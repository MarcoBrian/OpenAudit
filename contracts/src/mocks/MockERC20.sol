// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IERC20.sol";

/**
 * @title MockERC20
 * @notice Simple ERC-20 mock for testing (USDC-like, 6 decimals)
 */
contract MockERC20 is IERC20 {
    string  public name;
    string  public symbol;
    uint8   public decimals;

    uint256 private _totalSupply;
    mapping(address => uint256)                     private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    constructor(string memory _name, string memory _symbol, uint8 _decimals) {
        name     = _name;
        symbol   = _symbol;
        decimals = _decimals;
    }

    // ── Mint (test helper) ───────────────────────────────────────────────

    function mint(address to, uint256 amount) external {
        _balances[to] += amount;
        _totalSupply  += amount;
        emit Transfer(address(0), to, amount);
    }

    // ── ERC-20 ───────────────────────────────────────────────────────────

    function totalSupply() external view override returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) external view override returns (uint256) {
        return _balances[account];
    }

    function transfer(address to, uint256 amount) external override returns (bool) {
        require(_balances[msg.sender] >= amount, "ERC20: insufficient balance");
        _balances[msg.sender] -= amount;
        _balances[to]         += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function allowance(address owner_, address spender) external view override returns (uint256) {
        return _allowances[owner_][spender];
    }

    function approve(address spender, uint256 amount) external override returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        require(_balances[from] >= amount, "ERC20: insufficient balance");
        require(_allowances[from][msg.sender] >= amount, "ERC20: insufficient allowance");
        _balances[from]                  -= amount;
        _balances[to]                    += amount;
        _allowances[from][msg.sender]    -= amount;
        emit Transfer(from, to, amount);
        return true;
    }
}
