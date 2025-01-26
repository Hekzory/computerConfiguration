-- Core settings
vim.opt.number = true
vim.opt.mouse = "a"
vim.opt.termguicolors = true

-- Indentation
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.smartindent = true
vim.opt.expandtab = true -- Use spaces instead of tabs
vim.opt.autoindent = true

-- Editor Behavior
vim.opt.clipboard = "unnamedplus"
vim.opt.wrap = true -- Don't wrap lines
vim.opt.hlsearch = false -- Don't highlight search results
vim.opt.incsearch = true -- Incremental search
vim.opt.ignorecase = true
vim.opt.updatetime = 200 -- Faster updates

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

lazy.path = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
lazy.opts = {}

lazy.setup({
	install = { colorscheme = { "tokyonight" } },
	checker = { enabled = false }, -- update reminder is a bit intrusive
	spec = {
		{ "folke/tokyonight.nvim", lazy = false, priority = 1000 },
		{
			"nvim-lualine/lualine.nvim",
			dependencies = { "nvim-tree/nvim-web-devicons" },
			lazy = false,
		},
		{
			"neovim/nvim-lspconfig", -- REQUIRED: for native Neovim LSP integration
			lazy = false,
			dependencies = {
				-- main one
				{ "ms-jpq/coq_nvim", branch = "coq" },
				-- 9000+ Snippets
				{ "ms-jpq/coq.artifacts", branch = "artifacts" },
				-- lua & third party sources -- See https://github.com/ms-jpq/coq.thirdparty
				-- Need to **configure separately**
				{ "ms-jpq/coq.thirdparty", branch = "3p" },
			},
			init = function()
				vim.g.coq_settings = { auto_start = "shut-up" }
			end,
			config = function() end,
		},
		{ "lambdalisue/vim-suda" },
		{ "stevearc/conform.nvim", opts = {} },
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
				{ -- Use spaces instead of tabs

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
		{ "lukas-reineke/indent-blankline.nvim", main = "ibl", opts = {} },
		-- Auto pairs
		{ "windwp/nvim-autopairs", event = "InsertEnter", opts = {} },
	},
})

vim.g.suda_smart_edit = 1
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
		"gomod",
		"gosum",
		"cpp",
		"css",
		"html",
		"csv",
		"dockerfile",
		"gitignore",
		"html",
		"bash",
		"fish",
		"json",
		"make",
		"python",
		"rust",
		"sql",
		"udev",
		"yaml",
		"xml",
		"markdown_inline",
		"markdown",
		"cmake",
		"comment",
		-- "desktop", -- Does not work for now
		"diff",
		"git_config",
		"git_rebase",
		"gitattributes",
		"gitcommit",
		"java",
		"javascript",
		"json",
		"json5",
		"proto",
		"regex",
		"ssh_config",
		"toml",
	},
	sync_install = true,
	auto_install = true,
	highlight = { enable = true },
})

require("lspconfig").gopls.setup({})
require("lspconfig").ruff.setup({})

require("conform").setup({
	formatters = {
		yamlfmt = { prepend_args = { "-formatter", "max_line_length=240", "retain_line_breaks=true" } },
		taplo = { args = { "format", "--option", "indent_tables=true", "-" } },
		shfmt = { prepend_args = { "--indent", "4" } },
		prettier = { prepend_args = { "--print-width", "120", "--tab-width", "4", "--bracket-same-line" } },
	},
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
		bash = { "shfmt" },
		sh = { "shfmt" },
	},
	format_on_save = {
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

require("ibl").setup()
require("gitsigns").setup()

vim.cmd([[Neotree action=show toggle=true]])
vim.keymap.set("n", "<F2>", "<cmd>Neotree action=show toggle=true<CR>")
vim.keymap.set("n", "<F3>", "<cmd>Trouble diagnostics toggle focus=false filter.buf=0<CR>")
--vim.cmd([[ToggleTerm]])
