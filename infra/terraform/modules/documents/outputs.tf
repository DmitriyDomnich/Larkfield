output "bucket_name" {
  value = aws_s3_bucket.documents.id
}

output "api_policy_arn" {
  value = aws_iam_policy.api_documents.arn
}
