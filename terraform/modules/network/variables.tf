variable "name" {
  type        = string
  description = "Resource name prefix."
}

variable "vpc_cidr" {
  type        = string
  description = "VPC IPv4 CIDR."
}

variable "aws_region" {
  type        = string
  description = "Region used to form VPC endpoint service names."
}

