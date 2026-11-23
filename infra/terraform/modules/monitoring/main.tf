locals {
  namespace   = "Larkfield/${var.environment}"
  stages      = ["extraction", "review"]
  alarm_count = var.runtime_enabled ? 1 : 0
  token_widgets = {
    "Bedrock tokens per claim (average)" = "Average"
    "Bedrock tokens per claim (p90)"     = "p90"
  }
}

resource "aws_sns_topic" "alarms" {
  name = "${var.project_name}-alarms"
}

# confirmed once from the email; the topic outlives stop/start so the confirmation does too
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "claims_failed" {
  count               = local.alarm_count
  alarm_name          = "${var.project_name}-claims-failed"
  alarm_description   = "A claim went to failed (upload checks, extraction or review)."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  metric_query {
    id          = "failed"
    expression  = join(" + ", [for stage in local.stages : "FILL(${stage}, 0)"])
    label       = "Failed claims"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = toset(local.stages)
    content {
      id = metric_query.value
      metric {
        namespace   = local.namespace
        metric_name = "ClaimsFailed"
        dimensions  = { Stage = metric_query.value }
        period      = 300
        stat        = "Sum"
      }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  for_each            = var.runtime_enabled ? var.dead_letter_queues : {}
  alarm_name          = "${var.project_name}-${each.key}-dead-letters"
  alarm_description   = "A message in ${each.value} failed every delivery."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 300
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project_name
  dashboard_body = jsonencode({
    widgets = concat(
      [
        for index, title in keys(local.token_widgets) : {
          type   = "metric"
          x      = 12 * index
          y      = 0
          width  = 12
          height = 6
          properties = {
            title  = title
            region = var.aws_region
            stat   = local.token_widgets[title]
            period = 3600
            view   = "timeSeries"
            # one row per metric: [namespace, name, dimension, value, options]
            metrics = concat(
              [for stage in local.stages : [local.namespace, "BedrockInputTokens", "Stage", stage, { id = "${stage}_in", label = "${stage} input" }]],
              [for stage in local.stages : [local.namespace, "BedrockOutputTokens", "Stage", stage, { id = "${stage}_out", label = "${stage} output" }]],
              [[{
                expression = join(" + ", flatten([for stage in local.stages : ["FILL(${stage}_in, 0)", "FILL(${stage}_out, 0)"]]))
                label      = "both stages, input + output"
              }]],
            )
          }
        }
      ],
      [{
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "Failed claims"
          region  = var.aws_region
          stat    = "Sum"
          period  = 300
          view    = "timeSeries"
          metrics = [for stage in local.stages : [local.namespace, "ClaimsFailed", "Stage", stage]]
        }
      }],
    )
  })
}
