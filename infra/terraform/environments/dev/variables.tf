variable "aws_region" {
  type = string
}

variable "project" {
  type    = string
  default = "larkfield"
}

variable "environment" {
  description = "Prefixes every resource (<project>-<environment>-*) and tags it; the deploy role is scoped by both."
  type        = string
  default     = "dev"
}

variable "frontend_origins" {
  type    = list(string)
  default = ["http://localhost:3000"]
}

variable "bedrock_inference_profile_id" {
  description = "Inference profile the extraction worker calls (BEDROCK_MODEL_ID)."
  type        = string
}

variable "review_inference_profile_id" {
  description = "Inference profile the review worker calls (REVIEW_MODEL_ID)."
  type        = string
}

variable "ses_sender_email" {
  description = "From address of the claim emails; SES sends it a verification link."
  type        = string
}

variable "ses_recipient_emails" {
  description = "Demo recipients to verify while the account is in the SES sandbox."
  type        = list(string)
  default     = []
}
