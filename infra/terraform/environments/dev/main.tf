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

module "documents" {
  source           = "../../modules/documents"
  project_name     = var.project_name
  frontend_origins = var.frontend_origins
}

module "extraction" {
  source                       = "../../modules/extraction"
  project_name                 = var.project_name
  documents_bucket_name        = module.documents.bucket_name
  documents_bucket_arn         = module.documents.bucket_arn
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
}

module "knowledge_base" {
  source            = "../../modules/knowledge_base"
  project_name      = var.project_name
  source_dir        = "${path.root}/../../../../inputs/kb"
  clause_source_dir = "${path.root}/../../../../build/kb-clauses"
  chunking_strategies = {
    fixed = {
      fixed_size = { max_tokens = 300, overlap_percentage = 50 }
    }
    semantic = {
      semantic = { max_tokens = 400, buffer_size = 0, breakpoint_percentile_threshold = 95 }
    }
    hierarchical = {
      hierarchical = { parent_max_tokens = 600, child_max_tokens = 150, overlap_tokens = 30 }
    }
    clause = {
      source = "clauses"
    }
  }
}
