output "bucket_name" {
  value = aws_s3_bucket.policies.id
}

output "knowledge_base_ids" {
  value = { for name, kb in aws_bedrockagent_knowledge_base.policies : name => kb.id }
}

output "data_source_ids" {
  value = { for name, source in aws_bedrockagent_data_source.policies : name => source.data_source_id }
}
