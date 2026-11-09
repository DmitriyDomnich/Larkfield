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

output "extraction_queue_url" {
  value = module.extraction.queue_url
}

output "extraction_worker_policy_arn" {
  value = module.extraction.worker_policy_arn
}

output "policies_bucket" {
  value = module.knowledge_base.bucket_name
}

output "policy_knowledge_base_ids" {
  value = module.knowledge_base.knowledge_base_ids
}

output "policy_data_source_ids" {
  value = module.knowledge_base.data_source_ids
}
