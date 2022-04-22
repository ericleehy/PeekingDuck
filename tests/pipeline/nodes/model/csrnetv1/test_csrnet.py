# Copyright 2022 AI Singapore
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path
from unittest import TestCase, mock

import cv2
import pytest
import yaml

from peekingduck.pipeline.nodes.base import (
    PEEKINGDUCK_WEIGHTS_SUBDIR,
    WeightsDownloaderMixin,
)
from peekingduck.pipeline.nodes.model.csrnet import Node
from tests.conftest import PKD_DIR, do_nothing, get_groundtruth

GT_RESULTS = get_groundtruth(Path(__file__).resolve())


@pytest.fixture(params=["sparse", "dense"])
def csrnet_config(request):
    with open(PKD_DIR / "configs" / "model" / "csrnet.yml") as infile:
        node_config = yaml.safe_load(infile)
    node_config["root"] = Path.cwd()
    node_config["model_type"] = request.param

    return node_config


@pytest.fixture(
    params=[{"key": "width", "value": -1}, {"key": "width", "value": 0}],
)
def csrnet_bad_config_value(request, csrnet_config):
    csrnet_config[request.param["key"]] = request.param["value"]
    return csrnet_config


@pytest.mark.mlmodel
class TestCsrnet:
    def test_no_human(self, no_human_image, csrnet_config):
        no_human_img = cv2.imread(no_human_image)
        csrnet = Node(csrnet_config)
        output = csrnet.run({"img": no_human_img})
        assert list(output.keys()) == ["density_map", "count"]
        # Model is less accurate and detects extra people when count is low or
        # none. Threshold of 9 is chosen based on the min count in ShanghaiTech
        # dataset
        assert output["count"] < 9

    def test_crowd(self, crowd_image, csrnet_config):
        crowd_img = cv2.imread(crowd_image)
        csrnet = Node(csrnet_config)
        output = csrnet.run({"img": crowd_img})

        model_type = csrnet.config["model_type"]
        image_name = Path(crowd_image).stem
        expected = GT_RESULTS[model_type][image_name]

        assert list(output.keys()) == ["density_map", "count"]
        assert output["count"] == expected["count"]

    @mock.patch.object(WeightsDownloaderMixin, "_has_weights", return_value=False)
    @mock.patch.object(WeightsDownloaderMixin, "_download_to", wraps=do_nothing)
    @mock.patch.object(WeightsDownloaderMixin, "_extract_file", wraps=do_nothing)
    def test_no_weights(
        self,
        _,
        mock_download_to,
        mock_extract_file,
        csrnet_config,
    ):
        weights_dir = (
            csrnet_config["root"].parent
            / PEEKINGDUCK_WEIGHTS_SUBDIR
            / csrnet_config["weights"]["model_subdir"]
        )
        with TestCase.assertLogs(
            "peekingduck.pipeline.nodes.model.csrnetv1.csrnet_model.logger"
        ) as captured:
            csrnet = Node(config=csrnet_config)
            # records 0 - 20 records are updates to configs
            assert captured.records[0].getMessage() == "Proceeding to download..."
            assert (
                captured.records[1].getMessage()
                == f"Weights downloaded to {weights_dir}."
            )
            assert csrnet is not None

        assert mock_download_to.called
        assert mock_extract_file.called

    def test_invalid_config_value(self, csrnet_bad_config_value):
        with pytest.raises(ValueError) as excinfo:
            _ = Node(config=csrnet_bad_config_value)
        assert "must be more than 0" in str(excinfo.value)
