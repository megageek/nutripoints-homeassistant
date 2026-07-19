#!/usr/bin/env bash

set -euo pipefail

contract_version=$(tail -n 1 contract-version.txt)
contract_tag="v${contract_version}"
contract_asset="nutripoints_api_contracts-${contract_version}-py3-none-any.whl"

if [[ -n ${NUTRIPOINTS_CONTRACT_WHEEL:-} ]]; then
    log_header "Installing local Nutri Points API contract"
    uv pip install "${NUTRIPOINTS_CONTRACT_WHEEL}"
else
    contract_temp_dir=$(mktemp -d)
    trap 'rm -rf "${contract_temp_dir}"' EXIT

    log_header "Verifying Nutri Points API contract ${contract_version}"
    gh release download "${contract_tag}" \
        --repo megageek/nutripoints-api-contracts \
        --pattern "${contract_asset}" --pattern SHA256SUMS \
        --dir "${contract_temp_dir}"
    (
        cd "${contract_temp_dir}"
        sha256sum --check --strict SHA256SUMS
    )
    uv pip install "${contract_temp_dir}/${contract_asset}"
fi
