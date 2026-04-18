# Terraform configuration for SSOS cloud deployment

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "stadium_name" {
  description = "Name of the stadium"
  type        = string
  default     = "ssos-stadium"
}

locals {
  project_name = "ssos-${var.stadium_name}"
  tags = {
    Project     = "SSOS"
    Environment = "production"
    Stadium     = var.stadium_name
  }
}

resource "aws_vpc" "ssos_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.tags, { Name = "${local.project_name}-vpc" })
}

resource "aws_subnet" "private_subnet_1" {
  vpc_id            = aws_vpc.ssos_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.aws_region}a"

  tags = merge(local.tags, { Name = "${local.project_name}-private-1" })
}

resource "aws_subnet" "private_subnet_2" {
  vpc_id            = aws_vpc.ssos_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}b"

  tags = merge(local.tags, { Name = "${local.project_name}-private-2" })
}

resource "aws_subnet" "public_subnet" {
  vpc_id            = aws_vpc.ssos_vpc.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = merge(local.tags, { Name = "${local.project_name}-public" })
}

resource "aws_subnet" "public_subnet_2" {
  vpc_id            = aws_vpc.ssos_vpc.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}b"
  map_public_ip_on_launch = true

  tags = merge(local.tags, { Name = "${local.project_name}-public-2" })
}

resource "aws_internet_gateway" "ssos_igw" {
  vpc_id = aws_vpc.ssos_vpc.id

  tags = merge(local.tags, { Name = "${local.project_name}-igw" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.ssos_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ssos_igw.id
  }

  tags = merge(local.tags, { Name = "${local.project_name}-public-rt" })
}

resource "aws_route_table_association" "public_subnet_1" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_subnet_2" {
  subnet_id      = aws_subnet.public_subnet_2.id
  route_table_id = aws_route_table.public.id
}

resource "aws_ecs_cluster" "ssos_cluster" {
  name = local.project_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

resource "aws_ecs_task_definition" "api_gateway" {
  family                   = "api-gateway"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "api-gateway"
      image     = "ssos/api-gateway:latest"
      essential = true
      portMappings = [{
        containerPort = 8000
        protocol      = "tcp"
      }]
      environment = [
        { name = "REDIS_HOST", value = aws_elasticache_cluster.redis.address }
        { name = "KAFKA_BROKERS", value = aws_msk_cluster.kafka.bootstrap_brokers }
      ]
    }
  ])
}

resource "aws_ecs_service" "api_gateway_service" {
  name            = "api-gateway"
  cluster         = aws_ecs_cluster.ssos_cluster.id
  task_definition = aws_ecs_task_definition.api_gateway.arn
  desired_count   = 3
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_subnet_1.id, aws_subnet.private_subnet_2.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api_gateway.arn
    container_name   = "api-gateway"
    container_port   = 8000
  }
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${local.project_name}-redis"
  engine              = "redis"
  node_type           = "cache.t3.medium"
  num_cache_nodes     = 1
  parameter_group_name = "default.redis7"
  engine_version      = "7.0"
  port                = 6379

  tags = local.tags
}

resource "aws_msk_cluster" "kafka" {
  cluster_name           = "${local.project_name}-kafka"
  kafka_version         = "3.6.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    client_subnets = [aws_subnet.private_subnet_1.id, aws_subnet.private_subnet_2.id]
    storage_info {
      volume_size = 100
    }
  }

  tags = local.tags
}

resource "aws_db_instance" "postgres" {
  identifier           = "${local.project_name}-postgres"
  engine              = "postgres"
  engine_version      = "15.3"
  instance_class      = "db.t3.medium"
  allocated_storage   = 100
  max_allocated_storage = 500
  db_name             = "ssos_db"
  username            = "ssos"
  password            = var.db_password
  vpc_security_group_ids = [aws_security_group.rds.id]

  tags = local.tags
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${local.project_name}-ecs-tasks"
  vpc_id      = aws_vpc.ssos_vpc.id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_security_group" "rds" {
  name        = "${local.project_name}-rds"
  vpc_id      = aws_vpc.ssos_vpc.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  tags = local.tags
}

resource "aws_iam_role" "ecs_execution_role" {
  name = "${local.project_name}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_lb" "ssos_alb" {
  name               = "${local.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_subnet.id, aws_subnet.public_subnet_2.id]

  tags = local.tags
}

resource "aws_lb_target_group" "api_gateway" {
  name     = "${local.project_name}-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = aws_vpc.ssos_vpc.id
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.ssos_alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api_gateway.arn
  }
}

resource "aws_security_group" "alb" {
  name        = "${local.project_name}-alb"
  vpc_id      = aws_vpc.ssos_vpc.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

output "api_endpoint" {
  value = aws_lb.ssos_alb.dns_name
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.redis.address
}

output "kafka_brokers" {
  value = aws_msk_cluster.kafka.bootstrap_brokers
}
