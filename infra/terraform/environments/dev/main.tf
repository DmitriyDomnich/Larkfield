terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  backend "s3" {
    key          = "dev/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

module "iam" {
  source        = "../../modules/iam"
  project_name  = var.project_name
  user_pool_arn = module.cognito.user_pool_arn
}

module "lambda" {
  source          = "../../modules/lambda"
  project_name    = var.project_name
  lambda_role_arn = module.iam.lambda_role_arn
}

module "cognito" {
  source                       = "../../modules/cognito"
  project_name                 = var.project_name
  enable_password_auth         = true
  deletion_protection          = false
  post_confirmation_lambda_arn = module.lambda.post_confirmation_arn
}
