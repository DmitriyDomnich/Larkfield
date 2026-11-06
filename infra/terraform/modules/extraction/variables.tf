variable "project_name" {
  type = string
}

variable "documents_bucket_name" {
  type = string
}

variable "documents_bucket_arn" {
  description = "The bucket whose uploads under claims/ are sent to the queue."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Cross-Region inference profile the worker calls, e.g. eu.anthropic.claude-haiku-5-5."
  type        = string
}

variable "max_receives" {
  description = "Deliveries of one message before it moves to the dead-letter queue (EXTRACTION_MAX_RECEIVES)."
  type        = number
  default     = 3
}
