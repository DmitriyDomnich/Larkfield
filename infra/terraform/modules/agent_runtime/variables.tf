variable "project_name" {
  type = string
}

variable "iam_path" {
  description = "IAM path of the runtime's role; the deploy role manages only this path."
  type        = string
}

variable "permissions_boundary_arn" {
  type = string
}

variable "repository_url" {
  description = "ECR repository the deploy pushes `<image_tag>-agent-runtime` to."
  type        = string
}

variable "repository_arn" {
  type = string
}

variable "image_tag" {
  description = "Git SHA of the release; the runtime runs `<image_tag>-agent-runtime`."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Cross-Region inference profile the review agent calls (REVIEW_MODEL_ID)."
  type        = string
}

variable "policy_knowledge_base_id" {
  description = "The `clause` knowledge base the agent searches (POLICY_KB_ID)."
  type        = string
}

variable "environment_variables" {
  description = "The runtime's ReviewRuntimeSettings; 4 KB in total at most."
  type        = map(string)
}
