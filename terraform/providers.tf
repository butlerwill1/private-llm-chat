provider "aws" {
  region = var.aws_region

  default_tags {
    # Provider defaults cover every AWS resource type that supports tags, including
    # resources inside child modules. Resource-level Name tags are merged on top.
    tags = local.common_tags
  }
}
