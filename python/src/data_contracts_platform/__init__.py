"""Data contracts: validate them and classify every change as safe or breaking for consumers."""

from data_contracts_platform.contract import Contract, ContractError, load, loads, parse
from data_contracts_platform.diff import Change, diff, is_breaking

__all__ = ["Change", "Contract", "ContractError", "diff", "is_breaking", "load", "loads", "parse"]
__version__ = "0.1.0"
