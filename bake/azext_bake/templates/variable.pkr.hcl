variable "branch" {
  type        = string
  default     = ""
  description = "The branch to use for the build"
}

variable "commit" {
  type        = string
  default     = ""
  description = "The commit to use for the build"
}

variable "gallery" {
  type = object({
    name          = string
    resourceGroup = string
    subscription  = string
  })
  default = {
    name          = ""
    resourceGroup = ""
    subscription  = ""
  }
  description = "The azure compute gallery to publish the image"
}

variable "sandbox" {
  type = object({
    resourceGroup               = string
    subscription                = string
    virtualNetwork              = string
    virtualNetworkResourceGroup = string
    defaultSubnet               = string
    builderSubnet               = string
    keyVault                    = string
    storageAccount              = string
    identityId                  = string
  })
  default = {
    resourceGroup               = ""
    subscription                = ""
    virtualNetwork              = ""
    virtualNetworkResourceGroup = ""
    defaultSubnet               = ""
    builderSubnet               = ""
    keyVault                    = ""
    storageAccount              = ""
    identityId                  = ""
  }
  description = "The azure compute builder to use for the build"
}

variable "image" {
  type = object({
    name             = string
    version          = string
    replicaLocations = list(string)
    // subscription  = string
  })
  default = {
    name             = ""
    version          = ""
    replicaLocations = []
    subscription     = ""
  }
  description = "The azure compute image to publish"
}

variable "repos" {
  type = list(object({
    url    = string
    secret = string
  }))
  default     = []
  description = "The repositories to clone on the image"
}

