variable "environment_name" {
  type        = string
  description = "Environment name used in the resource group rg-credit-policy-<env>."
  default     = "credit-policy-demo"

  validation {
    condition     = length(var.environment_name) >= 1 && length(var.environment_name) <= 64
    error_message = "environment_name must be 1-64 characters."
  }
}

variable "location" {
  type        = string
  description = "Azure region. Default swedencentral. Blocked: eastus/eastus2/westus/westus3 (no new Search) and westus2 (no GlobalStandard gpt-5-mini)."
  default     = "swedencentral"

  validation {
    condition     = contains(["swedencentral", "uksouth", "francecentral", "canadaeast", "centralus"], var.location)
    error_message = "Location must be swedencentral or a documented backup (uksouth, francecentral, canadaeast, centralus)."
  }
}

variable "principal_id" {
  type        = string
  description = "Object ID of the deploying user or app. Empty uses the current Azure CLI principal."
  default     = ""
}

variable "chat_capacity" {
  type        = number
  description = "Chat deployment SKU capacity. 1 = 1000 TPM; default 50 = 50k TPM. Do not set 50000."
  default     = 50

  validation {
    condition     = var.chat_capacity >= 1 && var.chat_capacity <= 1000
    error_message = "chat_capacity is TPM thousands (50 = 50k TPM), not 50000."
  }
}

variable "embedding_capacity" {
  type        = number
  description = "Embedding deployment SKU capacity. 1 = 1000 TPM; default 20 = 20k TPM."
  default     = 20

  validation {
    condition     = var.embedding_capacity >= 1 && var.embedding_capacity <= 1000
    error_message = "embedding_capacity is TPM thousands (20 = 20k TPM)."
  }
}

variable "project_name" {
  type        = string
  description = "Foundry project name."
  default     = "credit-policy-demo"
}

variable "chat_deployment_name" {
  type        = string
  description = "Chat model deployment name."
  default     = "gpt-5-mini"
}

variable "embedding_deployment_name" {
  type        = string
  description = "Embedding model deployment name."
  default     = "text-embedding-3-large"
}
