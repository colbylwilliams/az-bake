# az-bake

Microsoft Azure CLI Custom Image Helper 'az' Extension adds useful "utilities" for common tasks.

## Sandbox

I

## Install

To install the Azure CLI Custom Image Helper extension, simply run the following command:

```sh
az extension add --source https://github.com/colbylwilliams/az-bake/releases/latest/download/bake-0.0.33-py3-none-any.whl -y
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

