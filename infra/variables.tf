variable "environment_name" {
  type        = string
  description = "Environment name used in the resource group rg-credit-policy-<env>. Must be dev1 or prd1."
  default     = "dev1"

  validation {
    condition     = contains(["dev1", "prd1"], var.environment_name)
    error_message = "environment_name must be dev1 or prd1."
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
