variable "name" {
  type        = string
  description = "Resource name prefix."
}

variable "ami_id" {
  type        = string
  description = "Hardened inference AMI ID."
  nullable    = true
}

variable "instance_type" {
  type        = string
  description = "GPU instance type."
}

variable "root_volume_gib" {
  type        = number
  description = "Root EBS size."
}

variable "kms_key_arn" {
  type        = string
  description = "KMS key for EBS encryption."
}

variable "subnet_id" {
  type        = string
  description = "Isolated subnet ID."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID."
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR used to constrain management egress."
}

variable "s3_prefix_list_id" {
  type        = string
  description = "S3 gateway endpoint prefix list ID."
}

variable "application_sg_id" {
  type        = string
  description = "Only this application security group may call inference."
}

variable "model_port" {
  type        = number
  description = "Private inference port."
}

variable "tags" {
  type        = map(string)
  description = "Standard cost-allocation tags inherited by the GPU and its EBS volume."
}
