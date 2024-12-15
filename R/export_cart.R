# Extract relevant information from the CARTs and save as JSON

library("tidyverse")
library("jsonlite")

to_json <- function(tree, fp) {

  # Convert rownames to columns as they contain important information: binary
  # node index for tree$frame and split variable for tree$splits
  #   - tree: rpart object
  #   - fp: file path to write JSON to

  frame <- tibble::rownames_to_column(tree$frame, var = "node")
  frame <- tibble::as_tibble(frame)

  splits <- tibble::as_tibble(tree$splits)

  # Add a "type" column to tree$splits to distringuish between main, primary and
  # surrogate splits
  n <- nrow(splits)
  nn <- frame$ncompete + frame$nsurrogate + !(frame$var == "<leaf>")
  ix <- cumsum(c(1L, nn))
  ix_prim <- unlist(
    mapply(ix, ix + c(frame$ncompete, 0), FUN = seq, SIMPLIFY = FALSE)
  )
  split_type <- rep.int("surrogate", n)
  split_type[ix_prim[ix_prim <= n]] <- "primary"
  split_type[ix[ix <= n]] <- "main"
  splits <- dplyr::mutate(splits, type = split_type)

  # Get "ncat" and "index" columns from tree$frame as they contain important
  # information: "ncat" provides info on split operator sign ("<" or ">") and
  # "index" is the corresponding row index in the "csplit" matrix.
  #
  # tree$frame and tree$splits are identically ordered - so as long as we only
  # consider main splits (excluding surrogate and primary) and skip leaves in
  # tree$frame, columns can be copied as they are.
  main_splits <- dplyr::filter(splits, type == "main")
  not_leaf <- frame$var != "<leaf>"
  ncat <- rep.int(0, nrow(frame))
  ncat[not_leaf] <- main_splits$ncat
  index <- rep.int(0, nrow(frame))
  index[not_leaf] <- main_splits$index
  frame <- dplyr::mutate(frame, ncat = ncat, index = index)

  frame <- dplyr::select(
    frame, "node", "var", "n", "yval", "ncat", "index", "yval2"
  )

  write_json(
    list(
      nodes = frame,
      ylevels = attr(tree, "ylevels"),
      xlevels = attr(tree, "xlevels"),
      csplit = tree$csplit
    ),
    fp
  )
}

tree <- readRDS("tree_rural_pruned.rds")
to_json(tree, "cart_rural.json")

tree <- readRDS("tree_urban_pruned.rds")
to_json(tree, "cart_urban.json")
