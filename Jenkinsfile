// Jenkins equivalent of the GitHub Actions CI pipeline.
// Needs a Jenkins agent with Docker, and a "ghcr-creds" username/password credential.
pipeline {
  agent any
  environment {
    IMAGE = "ghcr.io/palakgupta7456/aqi-forecaster"
  }
  options { timestamps(); timeout(time: 30, unit: 'MINUTES') }

  stages {
    stage('Setup') {
      steps {
        sh '''
          python3 -m venv .venv
          . .venv/bin/activate
          pip install -q -e ".[api,dev]"
        '''
      }
    }
    stage('Lint') {
      steps { sh '. .venv/bin/activate && ruff check .' }
    }
    stage('Train on synthetic data') {
      steps { sh '. .venv/bin/activate && python -m aqi.synthetic && python -m aqi.train' }
    }
    stage('Test') {
      steps { sh '. .venv/bin/activate && pytest --junitxml=reports/junit.xml' }
      post { always { junit 'reports/junit.xml' } }
    }
    stage('Build image') {
      steps { sh 'docker build -t $IMAGE:$GIT_COMMIT -t $IMAGE:latest .' }
    }
    stage('Push image') {
      when { branch 'main' }
      steps {
        withCredentials([usernamePassword(credentialsId: 'ghcr-creds', usernameVariable: 'U', passwordVariable: 'P')]) {
          sh 'echo $P | docker login ghcr.io -u $U --password-stdin && docker push $IMAGE:$GIT_COMMIT && docker push $IMAGE:latest'
        }
      }
    }
  }
  post { always { cleanWs() } }
}
