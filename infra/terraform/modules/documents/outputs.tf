output "bucket_name" {
  value = aws_s3_bucket.documents.id
}

output "bucket_arn" {
  value = aws_s3_bucket.documents.arn
}

output "api_policy_arn" {
  value = aws_iam_policy.api_documents.arn
}
