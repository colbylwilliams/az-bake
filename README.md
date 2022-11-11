# az-bake

Microsoft Azure CLI Custom Image 'az bake' Extension adds support for creating (or _"baking"_) custom VM images.

## Install

To install the Azure CLI Custom Image Helper extension, simply run the following command:

```sh
az extension add --source https://github.com/colbylwilliams/az-bake/releases/latest/download/bake-0.1.10-py3-none-any.whl -y
```

### Update

To update Azure CLI DevCenter Helper extension to the latest version:

```sh
az bake upgrade
```

or for the latest pre-release version:

```sh
az bake upgrade --pre
```

## Quickstart

#### 1. [Install](#install) the `az bake` Azure CLI extension

_After [installing the Azure CLI][install-az] if you haven't already_

#### 2. Create a new [sandbox](#sandbox)

```sh
az bake sandbox create --name MySandbox --gallery MyGallery
```

#### 3. Setup the repo

```sh
az bake repo setup --sandbox MySandbox --gallery MyGallery
```

#### 4. Create an image

```sh
az bake image create --name vscode-image
```

#### 5. Commit and push your changes

## Sandbox

In the context of `az bake`, a _sandbox_ is a collection of resources in a resource group that are used to create (or _"bake"_) custom VM images. It's a secure, self-contained environment where Packer will be executed from Azure Container Instance in a private virtual network. A sandbox is required to use `az bake`. You can be create a new sandbox using the `az bake sandbox create` command.

Each sandbox includes a:

- [Key Vault][azure-keyvault]
- [Storage Account][azure-storage-account]
- [Azure Container Instance (ACI) group][azure-aci-groups] for each custom image
- [Virtual Network][azure-vnet], with two subnets
  - A `default` subnet to which the temporary VMs will be joined. This also hosts a private endpoint for the Key Vault.
  - A `builders` subnet to which the ACI containers will be joined. This subnet must be set up to delegate access to ACI, and must only contain ACI container groups.
- [User-assigned Managed Identity][azure-identities] that is assigned to the ACI containers executing Packer and the temporary VMs. This identity will also require the [Contributor][azure-roles-contributor] role on the resource group that contains the [Azure Compute Gallery][azure-compute-gallery] where your custom images will be published.

![sandbox](docs/sandbox.png)

## Commands

This extension adds the following commands. Use `az bake -h` for more information.
| Command | Description |
| ------- | ----------- |
| [az bake repo](#az-bake-repo) | // TODO |

---

### `az bake repo`

// TODO

```sh
az bake repo
```

#### Examples

```sh
az bake repo

# output: user@example.com has valid licenses for dev box: ['SPE_E3']
```

[install-az]:https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
[azure-identities]:https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview
[azure-compute-gallery]:https://learn.microsoft.com/en-us/azure/virtual-machines/azure-compute-gallery
[azure-keyvault]:https://learn.microsoft.com/en-us/azure/key-vault/general/overview
[azure-storage-account]:https://learn.microsoft.com/en-us/azure/storage/common/storage-account-overview
[azure-aci]:https://learn.microsoft.com/en-us/azure/container-instances/container-instances-overview
[azure-aci-groups]:https://learn.microsoft.com/en-us/azure/container-instances/container-instances-container-groups
[azure-vnet]:https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview
[azure-roles-contributor]:https://docs.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#contributor
[azure-assign-rbac]:https://docs.microsoft.com/en-us/azure/role-based-access-control/role-assignments-portal?tabs=current
[gh-repo-secret]:https://docs.github.com/en/actions/reference/encrypted-secrets#creating-encrypted-secrets-for-a-repository
[gh-fork]:https://docs.github.com/en/get-started/quickstart/fork-a-repo
[packer-arm]:https://www.packer.io/plugins/builders/azure/arm
