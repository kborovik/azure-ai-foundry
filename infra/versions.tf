terraform {
  required_version = ">= 1.8.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 5.5.0"
    }
  }

  # storage_account_name + key come from `terraform init -backend-config`
  backend "azurerm" {
    resource_group_name = "rg-credit-policy-tfstate"
    container_name      = "tfstate"
    use_azuread_auth    = true
  }
}

provider "azurerm" {
  features {}
}
