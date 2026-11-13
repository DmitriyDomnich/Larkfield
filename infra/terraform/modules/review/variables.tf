variable "project_name" {
  type = string
}

variable "policy_knowledge_base_id" {
  description = "The `clause` knowledge base the agent searches (POLICY_KB_ID)."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Cross-Region inference profile the review agent calls (REVIEW_MODEL_ID)."
  type        = string
}

variable "max_receives" {
  description = "Deliveries of one request before it moves to the dead-letter queue (REVIEW_MAX_RECEIVES)."
  type        = number
  default     = 3
}
