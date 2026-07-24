data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gpu" {
  name               = "${var.name}-gpu"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.gpu.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "gpu" {
  name = "${var.name}-gpu"
  role = aws_iam_role.gpu.name
}

resource "aws_security_group" "gpu" {
  name_prefix = "${var.name}-gpu-"
  description = "Private inference host; no public ingress"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Inference from application workloads only"
    from_port       = var.model_port
    to_port         = var.model_port
    protocol        = "tcp"
    security_groups = [var.application_sg_id]
  }

  egress {
    description = "HTTPS to private interface endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description     = "HTTPS to S3 through gateway endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [var.s3_prefix_list_id]
  }

  egress {
    description = "DNS to VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["${cidrhost(var.vpc_cidr, 2)}/32"]
  }

  egress {
    description = "DNS over TCP to VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["${cidrhost(var.vpc_cidr, 2)}/32"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_instance" "gpu" {
  ami                                  = var.ami_id
  instance_type                        = var.instance_type
  subnet_id                            = var.subnet_id
  vpc_security_group_ids               = [aws_security_group.gpu.id]
  associate_public_ip_address          = false
  iam_instance_profile                 = aws_iam_instance_profile.gpu.name
  monitoring                           = true
  instance_initiated_shutdown_behavior = "stop"
  user_data_replace_on_change          = true

  # This watchdog runs on the instance, so it still stops chargeable compute if
  # the user's terminal, network or laptop disappears during a session.
  user_data = <<-CLOUD_INIT
    #cloud-config
    write_files:
      - path: /etc/systemd/system/private-chat-autostop.service
        permissions: '0644'
        content: |
          [Unit]
          Description=Stop private chat GPU after its maximum session time

          [Service]
          Type=oneshot
          ExecStart=/sbin/shutdown -h now
      - path: /etc/systemd/system/private-chat-autostop.timer
        permissions: '0644'
        content: |
          [Unit]
          Description=Hard cost-safety timer for the private chat GPU

          [Timer]
          OnBootSec=${var.max_runtime_minutes}min
          Unit=private-chat-autostop.service

          [Install]
          WantedBy=timers.target
    runcmd:
      - [systemctl, daemon-reload]
      - [systemctl, enable, --now, private-chat-autostop.timer]
  CLOUD_INIT

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    encrypted   = true
    kms_key_id  = var.kms_key_arn
    volume_size = var.root_volume_gib
    volume_type = "gp3"
  }

  # Provider defaults add the standard cost tags; this block adds GPU-specific
  # operational dimensions without duplicating the provider tag map.
  tags = {
    Name         = "${var.name}-gpu"
    Role         = "private-inference"
    ControlScope = var.name
    AutoStop     = "systemd-${var.max_runtime_minutes}m"
  }

  # Root EBS volumes are created indirectly by aws_instance, so pass the cost
  # allocation tags explicitly rather than relying only on provider defaults.
  volume_tags = merge(var.tags, {
    Name     = "${var.name}-gpu-root"
    Role     = "model-storage"
    AutoStop = "not-applicable"
  })

  lifecycle {
    precondition {
      condition     = var.ami_id != null
      error_message = "A hardened gpu_ami_id is required when the GPU module is enabled."
    }
  }
}
