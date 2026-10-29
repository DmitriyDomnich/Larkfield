data "archive_file" "post_confirmation" {
  type        = "zip"
  source_dir  = "${path.module}/../../../../lambdas/post_confirmation"
  output_path = "${path.root}/build/post_confirmation.zip"
}

resource "aws_lambda_function" "post_confirmation" {
  function_name    = "${var.project_name}-post-confirmation"
  role             = var.lambda_role_arn
  runtime          = "python3.13"
  handler          = "handler.handler"
  filename         = data.archive_file.post_confirmation.output_path
  source_code_hash = data.archive_file.post_confirmation.output_base64sha256
  timeout          = 5

  environment {
    variables = {
      DEFAULT_GROUP = "employee"
    }
  }
}
