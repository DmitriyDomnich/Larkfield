data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id          = data.aws_caller_identity.current.account_id
  region              = data.aws_region.current.region
  embedding_model_arn = "arn:aws:bedrock:${local.region}::foundation-model/${var.embedding_model_id}"
  content_types       = { md = "text/markdown", json = "application/json" }
  source_buckets = {
    documents = aws_s3_bucket.policies.arn
    clauses   = aws_s3_bucket.clauses.arn
  }
}

resource "aws_s3_bucket" "policies" {
  bucket_prefix = "${var.project_name}-policies-"
}

resource "aws_s3_bucket_public_access_block" "policies" {
  bucket                  = aws_s3_bucket.policies.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tls_only" {
  bucket     = aws_s3_bucket.policies.id
  depends_on = [aws_s3_bucket_public_access_block.policies]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.policies.arn, "${aws_s3_bucket.policies.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_object" "policy_files" {
  for_each     = fileset(var.source_dir, "*.{md,json}")
  bucket       = aws_s3_bucket.policies.id
  key          = each.value
  source       = "${var.source_dir}/${each.value}"
  source_hash  = filemd5("${var.source_dir}/${each.value}")
  content_type = local.content_types[reverse(split(".", each.value))[0]]
}

# one file per clause from `make kb-build`
resource "aws_s3_bucket" "clauses" {
  bucket_prefix = "${var.project_name}-clauses-"
}

resource "aws_s3_bucket_public_access_block" "clauses" {
  bucket                  = aws_s3_bucket.clauses.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "clauses_tls_only" {
  bucket     = aws_s3_bucket.clauses.id
  depends_on = [aws_s3_bucket_public_access_block.clauses]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.clauses.arn, "${aws_s3_bucket.clauses.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_object" "clause_files" {
  for_each     = fileset(var.clause_source_dir, "*/*.{md,json}")
  bucket       = aws_s3_bucket.clauses.id
  key          = each.value
  source       = "${var.clause_source_dir}/${each.value}"
  source_hash  = filemd5("${var.clause_source_dir}/${each.value}")
  content_type = local.content_types[reverse(split(".", each.value))[0]]
}

resource "aws_s3vectors_vector_bucket" "policies" {
  vector_bucket_name = "${var.project_name}-policies"
  force_destroy      = true
}


resource "aws_s3vectors_index" "policies" {
  for_each           = var.chunking_strategies
  vector_bucket_name = aws_s3vectors_vector_bucket.policies.vector_bucket_name
  index_name         = each.key
  data_type          = "float32"
  dimension          = var.embedding_dimensions
  distance_metric    = "cosine"

  metadata_configuration {
    non_filterable_metadata_keys = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
  }
}

resource "aws_iam_role" "knowledge_base" {
  name = "${var.project_name}-policies-kb"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock:${local.region}:${local.account_id}:knowledge-base/*" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "knowledge_base" {
  name = "ingest-and-query"
  role = aws_iam_role.knowledge_base.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EmbedText"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = local.embedding_model_arn
      },
      {
        Sid      = "ListPolicyFiles"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = values(local.source_buckets)
      },
      {
        Sid      = "ReadPolicyFiles"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = [for arn in values(local.source_buckets) : "${arn}/*"]
      },
      {
        Sid    = "ReadWriteVectors"
        Effect = "Allow"
        Action = [
          "s3vectors:PutVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:QueryVectors",
          "s3vectors:GetIndex",
        ]
        Resource = [for index in aws_s3vectors_index.policies : index.index_arn]
      },
    ]
  })
}

resource "aws_bedrockagent_knowledge_base" "policies" {
  for_each   = var.chunking_strategies
  name       = "${var.project_name}-policies-${each.key}"
  role_arn   = aws_iam_role.knowledge_base.arn
  depends_on = [aws_iam_role_policy.knowledge_base]

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.embedding_model_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.policies[each.key].index_arn
    }
  }
}

resource "aws_bedrockagent_data_source" "policies" {
  for_each          = var.chunking_strategies
  name              = "policies"
  knowledge_base_id = aws_bedrockagent_knowledge_base.policies[each.key].id

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = local.source_buckets[each.value.source]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = (
        each.value.fixed_size != null ? "FIXED_SIZE" :
        each.value.semantic != null ? "SEMANTIC" :
        each.value.hierarchical != null ? "HIERARCHICAL" : "NONE"
      )

      dynamic "fixed_size_chunking_configuration" {
        for_each = each.value.fixed_size[*]
        content {
          max_tokens         = fixed_size_chunking_configuration.value.max_tokens
          overlap_percentage = fixed_size_chunking_configuration.value.overlap_percentage
        }
      }

      dynamic "semantic_chunking_configuration" {
        for_each = each.value.semantic[*]
        content {
          max_token                       = semantic_chunking_configuration.value.max_tokens
          buffer_size                     = semantic_chunking_configuration.value.buffer_size
          breakpoint_percentile_threshold = semantic_chunking_configuration.value.breakpoint_percentile_threshold
        }
      }

      dynamic "hierarchical_chunking_configuration" {
        for_each = each.value.hierarchical[*]
        content {
          level_configuration {
            max_tokens = hierarchical_chunking_configuration.value.parent_max_tokens
          }
          level_configuration {
            max_tokens = hierarchical_chunking_configuration.value.child_max_tokens
          }
          overlap_tokens = hierarchical_chunking_configuration.value.overlap_tokens
        }
      }
    }
  }
}
