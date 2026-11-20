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
  default     = "prod"
}

variable "extra_frontend_origins" {
  description = "Origins besides the distribution's allowed by the documents bucket's CORS (the local frontend)."
  type        = list(string)
  default     = []
}

variable "alarm_email" {
  description = "Receives the alarms; confirm the SNS subscription email once."
  type        = string
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
  description = "Recipients the notification Lambda may email; verified through dev while the account is in the SES sandbox."
  type        = list(string)
  default     = []
}

variable "runtime_enabled" {
  description = "false = stopped: no NAT, ALB, RDS or ECS services. The workflows read it from SSM /<project>-<env>/runtime_enabled."
  type        = bool
  default     = false
}

variable "restore_db_snapshot" {
  description = "Create the database from the snapshot Stop took; the workflows set it when that snapshot exists."
  type        = bool
  default     = false
}

variable "db_password_version" {
  type    = number
  default = 1
}

variable "image_tag" {
  description = "Git SHA of the image the deploy pushed to ECR."
  type        = string
  default     = "none"
}
