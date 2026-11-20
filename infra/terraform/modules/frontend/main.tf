locals {
  s3_origin_id  = "site"
  api_origin_id = "api"
  # one route per page.tsx of the static export: claims/view/page.tsx -> /claims/view
  routes = [
    for page in fileset(var.frontend_app_dir, "**/page.tsx") :
    "/${join("/", [for segment in split("/", dirname(page)) : segment if segment != "." && !startswith(segment, "(")])}"
  ]
  # AWS managed cache and origin request policies
  caching_optimized      = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  caching_disabled       = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  all_viewer_except_host = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
}

resource "aws_s3_bucket" "site" {
  bucket_prefix = "${var.project_name}-site-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# releases/<sha>/ per deploy, copied to live/ (the origin path); a rollback copies an older release
resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  depends_on = [aws_s3_bucket_public_access_block.site]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "CloudFrontReadsLive"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/live/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.main.arn } }
      },
    ]
  })
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.project_name}-site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "site_paths" {
  name    = "${var.project_name}-site-paths"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = templatefile("${path.module}/functions/site_paths.js.tftpl", { routes = jsonencode(local.routes) })
}

resource "aws_cloudfront_function" "api_prefix" {
  name    = "${var.project_name}-api-prefix"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/functions/api_prefix.js")
}

resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${var.project_name}-security-headers"

  security_headers_config {
    # the page's <meta> CSP holds the rest; a meta CSP can't set frame-ancestors
    content_security_policy {
      content_security_policy = "frame-ancestors 'none'"
      override                = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

resource "aws_cloudfront_vpc_origin" "api" {
  count = var.runtime_enabled ? 1 : 0

  vpc_origin_endpoint_config {
    name                   = "${var.project_name}-api"
    arn                    = var.load_balancer_arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }
}

# created by CloudFront with the first VPC origin; admitting it lets only this account's
# distributions reach the ALB
data "aws_security_group" "cloudfront_vpc_origins" {
  count      = var.runtime_enabled ? 1 : 0
  vpc_id     = var.vpc_id
  name       = "CloudFront-VPCOrigins-Service-SG"
  depends_on = [aws_cloudfront_vpc_origin.api]
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  count                        = var.runtime_enabled ? 1 : 0
  security_group_id            = var.load_balancer_security_group_id
  referenced_security_group_id = data.aws_security_group.cloudfront_vpc_origins[0].id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  comment             = var.project_name
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"

  origin {
    origin_id                = local.s3_origin_id
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_path              = "/live"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  dynamic "origin" {
    for_each = var.runtime_enabled ? [1] : []
    content {
      origin_id   = local.api_origin_id
      domain_name = var.load_balancer_dns_name

      vpc_origin_config {
        vpc_origin_id       = aws_cloudfront_vpc_origin.api[0].id
        origin_read_timeout = 60
      }
    }
  }

  default_cache_behavior {
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.caching_optimized
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.site_paths.arn
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = var.runtime_enabled ? [1] : []
    content {
      path_pattern               = "/api/*"
      target_origin_id           = local.api_origin_id
      viewer_protocol_policy     = "https-only"
      allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = true
      cache_policy_id            = local.caching_disabled
      origin_request_policy_id   = local.all_viewer_except_host
      response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id

      function_association {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.api_prefix.arn
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
