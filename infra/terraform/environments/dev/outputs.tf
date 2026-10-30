output "region" {
  value = var.aws_region
}

output "user_pool_id" {
  value = module.cognito.user_pool_id
}

output "app_client_id" {
  value = module.cognito.app_client_id
}

output "documents_bucket" {
  value = module.documents.bucket_name
}

output "api_documents_policy_arn" {
  value = module.documents.api_policy_arn
}
