variable "location" {
  type        = string
  description = "Azure region for the tfstate resource group. Default swedencentral."
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
