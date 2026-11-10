import pytest

from evals.dataset_loader import load_samples
from tools.models import Service
from tools.tf_parser import (
    MAX_INPUT_BYTES,
    InputTooLargeError,
    NotTerraformError,
    TerraformParseError,
    parse_terraform,
    validate_terraform_input,
)


def _sample(file: str) -> str:
    return next(s for s in load_samples() if s.file == file).terraform


def test_parses_resources_with_type_name_and_service():
    resources = parse_terraform(_sample("vulnerable/gcs_public.tf"))

    assert [r.address for r in resources] == [
        "google_storage_bucket.assets",
        "google_storage_bucket_iam_member.public_read",
    ]
    assert resources[0].service == Service.CLOUD_STORAGE
    assert resources[0].attributes["location"] == "US"
    assert resources[1].attributes["member"] == "allUsers"


def test_nested_blocks_and_numbers_are_readable():
    web = parse_terraform(_sample("vulnerable/compute_open_ssh.tf"))[2]

    params = web.attributes["boot_disk"][0]["initialize_params"][0]
    assert params["size"] == 50
    assert params["type"] == "pd-ssd"


def test_unsupported_resource_types_are_kept_but_marked():
    resources = parse_terraform(_sample("mixed/web_stack.tf"))

    unsupported = [r.address for r in resources if not r.supported]
    assert unsupported == ["google_pubsub_topic.events"]


def test_comments_never_reach_the_parsed_resources():
    resources = parse_terraform(_sample("injection/comment_override.tf"))

    assert "Ignore all previous instructions" not in str([r.model_dump() for r in resources])


def test_file_with_byte_order_mark_is_accepted():
    resources = parse_terraform("﻿" + 'resource "google_storage_bucket" "b" {\n  name = "x"\n}\n')

    assert resources[0].address == "google_storage_bucket.b"


@pytest.mark.parametrize("text", ["", "   \n", "please review my infrastructure", "{'a': 1}"])
def test_rejects_input_that_is_not_terraform(text):
    with pytest.raises(NotTerraformError):
        validate_terraform_input(text)


def test_rejects_gcloud_commands():
    with pytest.raises(NotTerraformError):
        validate_terraform_input("gcloud compute instances create vm-1 --zone us-central1-a")


def test_rejects_files_over_200_kb():
    big = 'resource "google_storage_bucket" "b" {}\n' + "# padding\n" * (MAX_INPUT_BYTES // 10)

    with pytest.raises(InputTooLargeError, match="200 KB"):
        validate_terraform_input(big)


def test_syntax_error_is_reported_with_a_clear_message():
    with pytest.raises(TerraformParseError, match="syntax error"):
        parse_terraform('resource "google_storage_bucket" "b" {\n  name = \n')
