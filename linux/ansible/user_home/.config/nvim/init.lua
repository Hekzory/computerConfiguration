vim.opt.number = true
vim.opt.mouse = "a"
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.smartindent = true
vim.opt.clipboard = "unnamedplus"

--vim.keymap.set({ "n", "x" }, "gy", '"+y')
--vim.keymap.set({ "n", "x" }, "gp", '"+p')

local lazy = {}

function lazy.install(path)
	if not (vim.uv or vim.loop).fs_stat(path) then
		print("Installing lazy.nvim....")
		vim.fn.system({
			"git",
			"clone",
			"--filter=blob:none",
			"https://github.com/folke/lazy.nvim.git",
			"--branch=stable", -- latest stable release
			path,
		})
	end
end

function lazy.setup(plugins)
	if vim.g.plugins_ready then
		return
	end

	lazy.install(lazy.path)

	vim.opt.rtp:prepend(lazy.path)

	require("lazy").setup(plugins, lazy.opts)
	vim.g.plugins_ready = true
end

vim.g.suda_smart_edit = 1

lazy.path = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
lazy.opts = {}

lazy.setup({
	{ "folke/tokyonight.nvim", lazy = false, priority = 1000 },
	{
		"nvim-lualine/lualine.nvim",
		dependencies = { "nvim-tree/nvim-web-devicons" },
		lazy = false,
	},
	{
		"neovim/nvim-lspconfig", -- REQUIRED: for native Neovim LSP integration
		lazy = false,
		dependencies = {},
		init = function() end,
		config = function() end,
	},
	{
		"lambdalisue/vim-suda",
	},
	{
		"stevearc/conform.nvim",
		opts = {},
	},
	{
		"nvim-treesitter/nvim-treesitter",
		build = ":TSUpdate",
	},
	{
		"nvim-neo-tree/neo-tree.nvim",
		lazy = false,
		branch = "v3.x",
		dependencies = {
			"nvim-lua/plenary.nvim",
			"nvim-tree/nvim-web-devicons", -- not strictly required, but recommended
			"MunifTanjim/nui.nvim",
			-- "3rd/image.nvim", -- Optional image support in preview window: See `# Preview Mode` for more information
		},
	},
	{
		"folke/trouble.nvim",
		opts = {}, -- for default options, refer to the configuration section for custom setup.
		cmd = "Trouble",
		keys = {
			{
				"<leader>cs",
				"<cmd>Trouble symbols toggle focus=false<cr>",
				desc = "Symbols (Trouble)",
			},
			{
				"<leader>cl",
				"<cmd>Trouble lsp toggle focus=false win.position=right<cr>",
				desc = "LSP Definitions / references / ... (Trouble)",
			},
			{
				"<leader>xL",
				"<cmd>Trouble loclist toggle<cr>",
				desc = "Location List (Trouble)",
			},
			{
				"<leader>xQ",
				"<cmd>Trouble qflist toggle<cr>",
				desc = "Quickfix List (Trouble)",
			},
		},
	},
	{ "akinsho/toggleterm.nvim", version = "*", config = true },
	{ "lewis6991/gitsigns.nvim", opts = {} },
})

vim.opt.termguicolors = true
vim.cmd([[colorscheme tokyonight-moon]])

require("lualine").setup({
	options = { theme = "tokyonight-moon", globalstatus = true },
})

require("neo-tree").setup({
	close_if_last_window = true,
	enable_git_status = true,
	filesystem = {
		filtered_items = {
			hide_dotfiles = false,
			hide_hidden = false,
		},
	},
})

require("nvim-treesitter.configs").setup({
	ensure_installed = {
		"c",
		"lua",
		"vim",
		"vimdoc",
		"query",
		"go",
		"cpp",
		"css",
		"html",
		"csv",
		"dockerfile",
		"gitignore",
		"html",
		"bash",
		"json",
		"make",
		"python",
		"rust",
		"sql",
		"udev",
		"yaml",
		"xml",
	},
	sync_install = true,
	auto_install = true,
	highlight = {
		enable = true,
	},
})

require("lspconfig").gopls.setup({})
require("lspconfig").ruff.setup({})

require("conform").formatters.yamlfmt = {
	prepend_args = { "-formatter", "max_line_length=120" },
}

require("conform").formatters.taplo = {
	args = { "format", "--option", "indent_tables=true", "-" },
}

require("conform").formatters.prettier = {
	prepend_args = { "--print-width", "120", "--tab-width", "4", "--bracket-same-line" },
}

require("conform").setup({
	formatters_by_ft = {
		lua = { "stylua" },
		yaml = { "yamlfmt" },
		xml = { "xmllint" },
		svg = { "xmllint" },
		toml = { "taplo" },
		javascript = { "prettier" },
		html = { "prettier" },
		css = { "prettier" },
		js = { "prettier" },
		markdown = { "prettier" },
		json = { "prettier" },
		typescript = { "prettier" },
	},
})

require("conform").setup({
	format_on_save = {
		-- These options will be passed to conform.format()
		timeout_ms = 500,
		lsp_fallback = true,
	},
})

require("toggleterm").setup({
	open_mapping = "<F4>",
	insert_mappings = true,
	terminal_mappings = true,
	close_on_exit = true,
	size = 7,
})

require("gitsigns").setup()

vim.cmd([[Neotree action=show toggle=true]])
vim.keymap.set("n", "<F2>", "<cmd>Neotree action=show toggle=true<CR>")
vim.keymap.set("n", "<F3>", "<cmd>Trouble diagnostics toggle focus=false filter.buf=0<CR>")
--vim.cmd([[ToggleTerm]])
