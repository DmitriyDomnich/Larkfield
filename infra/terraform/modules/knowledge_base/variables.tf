variable "project_name" {
  type = string
}

variable "source_dir" {
  description = "Directory with the policy .md files and their .metadata.json sidecars (inputs/kb)."
  type        = string
}

variable "clause_source_dir" {
  description = "Directory with one .md file and .metadata.json sidecar per clause (make kb-build)."
  type        = string
}

variable "embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  type    = number
  default = 1024
}

variable "chunking_strategies" {
  description = "One knowledge base per entry. Set at most one of fixed_size, semantic or hierarchical; none means NONE (one file = one chunk). source: documents or clauses."
  type = map(object({
    source = optional(string, "documents")
    fixed_size = optional(object({
      max_tokens         = number
      overlap_percentage = number
    }))
    semantic = optional(object({
      max_tokens                      = number
      buffer_size                     = number
      breakpoint_percentile_threshold = number
    }))
    hierarchical = optional(object({
      parent_max_tokens = number
      child_max_tokens  = number
      overlap_tokens    = number
    }))
  }))

  validation {
    condition = alltrue([
      for strategy in values(var.chunking_strategies) :
      length([for config in [strategy.fixed_size, strategy.semantic, strategy.hierarchical] : config if config != null]) <= 1
    ])
    error_message = "Each chunking strategy sets at most one of fixed_size, semantic or hierarchical."
  }

  validation {
    condition     = alltrue([for strategy in values(var.chunking_strategies) : contains(["documents", "clauses"], strategy.source)])
    error_message = "A chunking strategy's source is documents or clauses."
  }
}
