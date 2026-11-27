output "domain_name" {
  value = aws_cloudfront_distribution.main.domain_name
}

output "distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "site_bucket" {
  value = aws_s3_bucket.site.id
}
