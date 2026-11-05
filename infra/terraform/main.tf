# Serverless deployment of the FastAPI container on AWS Lambda (free-tier friendly).
# Usage (run by .github/workflows/deploy-aws.yml):
#   terraform init && terraform apply -var image_tag=<git sha>

terraform {
  required_version = ">= 1.6"
  # State lives in your own S3 bucket (TF_STATE_BUCKET secret) so repeated deploys update, not duplicate
  backend "s3" {
    key    = "aqi-forecaster/terraform.tfstate"
    region = "ap-south-1"
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "ap-south-1" # Mumbai
}

variable "image_tag" {
  type = string
}

variable "model_url" {
  type        = string
  description = "Public URL of model.joblib on the live-data branch"
}

resource "aws_ecr_repository" "api" {
  name                 = "aqi-forecaster"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "keep_last_5" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1, description = "Keep last 5 images",
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 },
      action       = { type = "expire" }
    }]
  })
}

resource "aws_iam_role" "lambda" {
  name = "aqi-forecaster-lambda"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "api" {
  function_name = "aqi-forecaster-api"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
  memory_size   = 1024
  timeout       = 60
  architectures = ["x86_64"]
  environment {
    variables = {
      PORT                            = "8000"
      MODEL_URL                       = var.model_url
      AWS_LWA_READINESS_CHECK_PATH    = "/health"
      AWS_LWA_ASYNC_INIT              = "true"
    }
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"
  cors {
    allow_origins = ["*"]
    allow_methods = ["GET"]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = 7
}

output "api_url" {
  value = aws_lambda_function_url.api.function_url
}

output "ecr_repository" {
  value = aws_ecr_repository.api.repository_url
}
