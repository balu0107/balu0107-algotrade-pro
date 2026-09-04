data "aws_ami" "ubuntu" {
  most_recent = true
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  owners = ["099720109477"]
}

resource "aws_instance" "k8s_master" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.master_instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.k8s_cluster_sg.id]
  key_name                    = var.key_name
  associate_public_ip_address = true

  root_block_device {
    volume_size           = 25
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "corp-k8s-master-node" }
}

resource "aws_instance" "k8s_worker_1" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.worker_instance_type
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.k8s_cluster_sg.id]
  key_name               = var.key_name

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "corp-k8s-worker-node-1" }
}

resource "aws_instance" "k8s_worker_2" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.worker_instance_type
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.k8s_cluster_sg.id]
  key_name               = var.key_name

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "corp-k8s-worker-node-2" }
}

resource "aws_key_pair" "generated_key" {
  key_name   = var.key_name
  public_key = file("${path.module}/my-k8s-key.pub")
}