terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  backend "s3" {
    key          = "prod/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix      = "${var.project}-${var.environment}"
  iam_path         = "/${local.name_prefix}/"
  boundary_arn     = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.project}-bootstrap/${local.name_prefix}-boundary"
  frontend_origins = concat(["https://${module.frontend.domain_name}"], var.extra_frontend_origins)
}

module "iam" {
  source                   = "../../modules/iam"
  project_name             = local.name_prefix
  iam_path                 = local.iam_path
  permissions_boundary_arn = local.boundary_arn
  user_pool_arn            = module.cognito.user_pool_arn
}

module "lambda" {
  source          = "../../modules/lambda"
  project_name    = local.name_prefix
  lambda_role_arn = module.iam.lambda_role_arn
}

module "cognito" {
  source                       = "../../modules/cognito"
  project_name                 = local.name_prefix
  enable_password_auth         = false
  deletion_protection          = true
  post_confirmation_lambda_arn = module.lambda.post_confirmation_arn
}

module "documents" {
  source           = "../../modules/documents"
  project_name     = local.name_prefix
  iam_path         = local.iam_path
  frontend_origins = local.frontend_origins
}

module "extraction" {
  source                       = "../../modules/extraction"
  project_name                 = local.name_prefix
  iam_path                     = local.iam_path
  documents_bucket_name        = module.documents.bucket_name
  documents_bucket_arn         = module.documents.bucket_arn
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
  review_queue_arn             = module.review.queue_arn
}

module "knowledge_base" {
  source                   = "../../modules/knowledge_base"
  project_name             = local.name_prefix
  iam_path                 = local.iam_path
  permissions_boundary_arn = local.boundary_arn
  source_dir               = "${path.root}/../../../../inputs/kb"
  clause_source_dir        = "${path.root}/../../../../build/kb-clauses"
  chunking_strategies = {
    clause = {
      source = "clauses"
    }
  }
}

module "review" {
  source                       = "../../modules/review"
  project_name                 = local.name_prefix
  iam_path                     = local.iam_path
  policy_knowledge_base_id     = module.knowledge_base.knowledge_base_ids["clause"]
  bedrock_inference_profile_id = var.review_inference_profile_id
}

module "notifications" {
  source                   = "../../modules/notifications"
  project_name             = local.name_prefix
  iam_path                 = local.iam_path
  permissions_boundary_arn = local.boundary_arn
  user_pool_id             = module.cognito.user_pool_id
  user_pool_arn            = module.cognito.user_pool_arn
  sender_email             = var.ses_sender_email
  recipient_emails         = var.ses_recipient_emails
  manage_email_identities  = false
}

module "network" {
  source          = "../../modules/network"
  project_name    = local.name_prefix
  runtime_enabled = var.runtime_enabled
}

module "database" {
  source           = "../../modules/database"
  project_name     = local.name_prefix
  runtime_enabled  = var.runtime_enabled
  restore_snapshot = var.restore_db_snapshot
  password_version = var.db_password_version
  apply_password   = var.apply_db_password
  vpc_id           = module.network.vpc_id
  subnet_ids       = module.network.private_subnet_ids
}

module "runtime" {
  source                       = "../../modules/runtime"
  project_name                 = local.name_prefix
  runtime_enabled              = var.runtime_enabled
  image_tag                    = var.image_tag
  iam_path                     = local.iam_path
  permissions_boundary_arn     = local.boundary_arn
  vpc_id                       = module.network.vpc_id
  private_subnet_ids           = module.network.private_subnet_ids
  database_url                 = module.database.url_without_password
  database_password_secret_arn = module.database.password_secret_arn
  database_security_group_id   = module.database.security_group_id
  user_pool_arn                = module.cognito.user_pool_arn

  shared_environment = {
    APP_ENV                = var.environment
    LOG_LEVEL              = "INFO"
    AWS_REGION             = var.aws_region
    COGNITO_REGION         = var.aws_region
    COGNITO_USER_POOL_ID   = module.cognito.user_pool_id
    COGNITO_APP_CLIENT_ID  = module.cognito.app_client_id
    DOCUMENTS_BUCKET       = module.documents.bucket_name
    REVIEW_QUEUE_URL       = module.review.queue_url
    NOTIFICATION_QUEUE_URL = module.notifications.queue_url
    FRONTEND_ORIGINS       = jsonencode(local.frontend_origins)
  }
  extraction_environment = {
    EXTRACTION_QUEUE_URL = module.extraction.queue_url
    BEDROCK_MODEL_ID     = var.bedrock_inference_profile_id
  }
  review_environment = {
    REVIEW_MODEL_ID = var.review_inference_profile_id
    POLICY_KB_ID    = module.knowledge_base.knowledge_base_ids["clause"]
  }

  api_policy_arns = {
    documents     = module.documents.api_policy_arn
    review        = module.review.api_policy_arn
    notifications = module.notifications.sender_policy_arn
  }
  extraction_policy_arns = {
    worker        = module.extraction.worker_policy_arn
    notifications = module.notifications.sender_policy_arn
  }
  review_policy_arns = {
    worker        = module.review.worker_policy_arn
    notifications = module.notifications.sender_policy_arn
  }
}

module "frontend" {
  source                          = "../../modules/frontend"
  project_name                    = local.name_prefix
  runtime_enabled                 = var.runtime_enabled
  frontend_app_dir                = "${path.root}/../../../../frontend/src/app"
  vpc_id                          = module.network.vpc_id
  load_balancer_arn               = module.runtime.load_balancer_arn
  load_balancer_dns_name          = module.runtime.load_balancer_dns_name
  load_balancer_security_group_id = module.runtime.load_balancer_security_group_id
}

module "monitoring" {
  source          = "../../modules/monitoring"
  project_name    = local.name_prefix
  environment     = var.environment
  aws_region      = var.aws_region
  runtime_enabled = var.runtime_enabled
  alarm_email     = var.alarm_email
  dead_letter_queues = {
    extraction    = module.extraction.dlq_name
    review        = module.review.dlq_name
    notifications = module.notifications.dlq_name
  }
}
