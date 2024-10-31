Python package that includes modules and tools to produce IASO forms from Classification And
Regression Trees (CART) models. The package is used to produce the typing tools used in the Pathways
project data collection campaigns (https://www.projectpathways.org/home).

- [Installation](#installation)
- [Usage](#usage)
    - [Building trees from CARTs](#building-trees-from-carts)
    - [Traversing trees](#traversing-trees)
    - [Working with nodes](#working-with-nodes)
    - [Merging trees](#merging-trees)

# Installation

Package is in development and not yet published to Pypi.

Install directly from the Git repo:

```
pip install git+https://github.com/BLSQ/pathways-typing@main
```

# Usage

## Building trees from CARTs

The package expect JSON outputs from an R `rpart` model object. The JSON file can be generated in R from the `rpart` object using the following code snippet:

``` R
library("rpart")
library("jsonlite")

frame <- tree$frame
frame$node_index <- row.names(frame)
frame$label <- labels(tree, minlength = 0)
write(toJSON(frame), "cart_rural.json")
```

To build the binary tree in Python:

``` python
with open("cart.json") as f:
    frame = json.load(f)
root = build_binary_tree(frame, strata="rural")
print(root)
```
```
>>> SurveyNode('wealth_sum_5595b726')
```

The function returns the root node of the tree.

## Traversing trees

You can iterate in pre- or post-order starting from any node:

``` python
for node in root.preorder():
    print(node.uid)
```
```
wealth_sum wealth_sum_5595b726
malaria_zone malaria_zone_c579eafd
hh_electricity hh_electricity_fbaa8a13
...
segment segment_79b48e84
segment segment_209ff0ee
```

## Working with nodes

`Node` objects can have 0 or 1 parent, and 0 or more children. They posess the following attributes:

* `name`: node name, which uses the CART split variable by default (ex: "hh_electricity")
* `uid`: unique node ID, which uses the CART split variable with a random suffix (ex: "hh_electricity_fbaa8a13")
* `children`: the children of the current node (none if leaf)
* `parent`: the parent of the current node (none if root)
* `data`: a dictionary to store CART-related data (node index, split rule, left or right child)
* `is_leaf`
* `is_root`

## Merging trees

Urban and rural trees can be merged using `merge_trees()`. A new root node will be created with the name `"location"`. Both urban & rural root nodes will be updated to appear as the left and right children of the new root.

``` python
print(urban_root.is_root)
```
```
>>> True
```

``` python
root = merge_trees(urban_root, rural_root)
print(urban_root.is_root)
```
```
>>> False
```
