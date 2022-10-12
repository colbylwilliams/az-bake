# az-bake

Microsoft Azure CLI Custom Image Helper 'az' Extension adds useful "utilities" for common tasks.

## Install

To install the Azure CLI Custom Image Helper extension, simply run the following command:

```sh
az extension add --source https://github.com/colbylwilliams/az-bake/releases/latest/download/bake-0.0.7-py3-none-any.whl -y
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

## Commands

This extension adds the following commands.  Use `az bake -h` for more information.
| Command | Description |
| ------- | ----------- |
| [az bake user check](#az-bake-user-check) | Check if a user has appropriate licenses to use dev box. |

---

### `az bake user check`

Check if a user has appropriate licenses to use dev box.

```sh
az bake user check --user
```

#### Examples

```sh
az bake user check --user user@example.com

# output: user@example.com has valid licenses for dev box: ['SPE_E3']
```

