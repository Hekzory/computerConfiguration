vim.loader.enable()

-- Core settings
vim.g.mapleader = " " -- <Space> as leader
vim.opt.number = true
vim.opt.mouse = "a"
vim.opt.mousemoveevent = true -- Enable mouse move events (useful for hover features)
vim.opt.termguicolors = true
vim.opt.list = true -- Show invisible characters
vim.opt.listchars = { tab = "» ", trail = "·", nbsp = "␣" }

-- Indentation
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.smartindent = true
vim.opt.expandtab = true -- Use spaces instead of tabs

-- Editor Behavior
vim.opt.clipboard = "unnamedplus"
vim.opt.wrap = false -- No wrap lines
vim.opt.hlsearch = false -- Don't highlight search results
vim.opt.incsearch = true -- Incremental search
vim.opt.smartcase = true
vim.opt.updatetime = 150 -- Faster updates
vim.opt.timeoutlen = 1000
vim.g.loaded_ruby_provider = 0
vim.g.loaded_perl_provider = 0

vim.opt.cursorline = true
vim.opt.cursorlineopt = "number"
vim.opt.signcolumn = "yes"
vim.opt.scrolloff = 4
vim.opt.sidescrolloff = 8
vim.opt.showmode = false
vim.opt.smoothscroll = true

vim.keymap.set("n", "<leader>ff", "<cmd>Telescope find_files<CR>", { desc = "Find files" })
vim.keymap.set("n", "<leader>fg", "<cmd>Telescope live_grep<CR>", { desc = "Find text" })
vim.keymap.set("n", "<leader>fb", "<cmd>Telescope buffers<CR>", { desc = "Buffers" })
vim.keymap.set("n", "<leader>w", "<cmd>w<CR>", { desc = "Save file" })
vim.keymap.set("n", "<leader>q", "<cmd>q<CR>", { desc = "Quit" })
vim.keymap.set("n", "<leader>e", "<cmd>Neotree toggle<CR>", { desc = "Toggle Explorer" })

local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not (vim.uv or vim.loop).fs_stat(lazypath) then
	vim.fn.system({
		"git",
		"clone",
		"--filter=blob:none",
		"https://github.com/folke/lazy.nvim.git",
		"--branch=stable",
		lazypath,
	})
end
vim.opt.rtp:prepend(lazypath)

require("lazy").setup({
	install = { colorscheme = { "tokyonight" } },
	checker = { enabled = false }, -- update reminder is a bit intrusive
	spec = {
		{ "folke/tokyonight.nvim", lazy = false, priority = 1000 },
		{
			"nvim-lualine/lualine.nvim",
			dependencies = { "nvim-tree/nvim-web-devicons" },
			lazy = false,
			opts = {
				options = { theme = "tokyonight-moon", globalstatus = true },
			},
		},
		{
			"neovim/nvim-lspconfig",
			lazy = false,
		},
		{
			"hrsh7th/nvim-cmp",
			event = "InsertEnter",
			dependencies = {
				"hrsh7th/cmp-nvim-lsp",
				"hrsh7th/cmp-buffer",
				"hrsh7th/cmp-path",
				{ "hrsh7th/cmp-cmdline", event = "CmdlineEnter" },
				"L3MON4D3/LuaSnip", -- Snippet engine
				"saadparwaiz1/cmp_luasnip", -- Snippet source for nvim-cmp
				"onsails/lspkind.nvim", -- VSCode-like pictograms for completion items
				"rafamadriz/friendly-snippets", -- Useful snippets collection
			},
			config = function()
				local cmp = require("cmp")
				local luasnip = require("luasnip")
				local lspkind = require("lspkind")

				-- Load friendly-snippets
				require("luasnip.loaders.from_vscode").lazy_load()

				cmp.setup({
					snippet = {
						expand = function(args)
							luasnip.lsp_expand(args.body)
						end,
					},
					mapping = cmp.mapping.preset.insert({
						["<C-b>"] = cmp.mapping.scroll_docs(-4),
						["<C-f>"] = cmp.mapping.scroll_docs(4),
						["<C-Space>"] = cmp.mapping.complete(),
						["<C-e>"] = cmp.mapping.abort(),
						["<CR>"] = cmp.mapping.confirm({ select = true }),
						["<Tab>"] = cmp.mapping(function(fallback)
							if cmp.visible() then
								cmp.select_next_item()
							elseif luasnip.expand_or_jumpable() then
								luasnip.expand_or_jump()
							else
								fallback()
							end
						end, { "i", "s" }),
						["<S-Tab>"] = cmp.mapping(function(fallback)
							if cmp.visible() then
								cmp.select_prev_item()
							elseif luasnip.jumpable(-1) then
								luasnip.jump(-1)
							else
								fallback()
							end
						end, { "i", "s" }),
					}),
					sources = cmp.config.sources({
						{ name = "nvim_lsp" },
						{ name = "luasnip" },
					}, {
						{ name = "buffer" },
						{ name = "path" },
					}),
					window = {
						completion = cmp.config.window.bordered(),
						documentation = cmp.config.window.bordered(),
					},
					formatting = {
						format = lspkind.cmp_format({
							mode = "symbol_text", -- Show symbol and text
							maxwidth = 50, -- Truncate item text if it's too long
							ellipsis_char = "...", -- Character to use for truncation
							-- Define how different completion item kinds are displayed.
							-- For more advanced configuration, see lspkind documentation.
							symbol_map = {
								Text = "󰉿",
								Method = "󰆧",
								Function = "󰊕",
								Constructor = "",
								Field = "󰜢",
								Variable = "󰀫",
								Class = "󰠱",
								Interface = "",
								Module = "",
								Property = "󰜢",
								Unit = "󰑭",
								Value = "󰎠",
								Enum = "",
								Keyword = "󰌋",
								Snippet = "",
								Color = "󰏘",
								File = "󰈙",
								Reference = "󰈇",
								Folder = "󰉋",
								EnumMember = "",
								Constant = "󰏿",
								Struct = "󰙅",
								Event = "",
								Operator = "󰆕",
								TypeParameter = "󰊄",
							},
						}),
					},
					experimental = {
						ghost_text = true,
					},
				})

				-- Setup for command line
				cmp.setup.cmdline({ "/", "?" }, {
					mapping = cmp.mapping.preset.cmdline(),
					sources = {
						{ name = "buffer" },
					},
				})

				cmp.setup.cmdline(":", {
					mapping = cmp.mapping.preset.cmdline(),
					sources = cmp.config.sources({
						{ name = "path" },
					}, {
						{ name = "cmdline" },
					}),
				})
			end,
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
				"nvim-tree/nvim-web-devicons",
				"MunifTanjim/nui.nvim",
			},
			opts = {
				close_if_last_window = true,
				enable_git_status = true,
				enable_diagnostics = true,
				default_component_configs = {
					git_status = {
						symbols = {
							added = "",
							modified = "",
							deleted = "✖",
							renamed = "➜",
							untracked = "★",
							ignored = "◌",
							unstaged = "✗",
							staged = "✓",
							conflict = "??",
						},
					},
				},
				window = {
					width = 35,
					mappings = {
						["<space>"] = "none",
						["<2-LeftMouse>"] = "open",
						["<cr>"] = "open",
						["l"] = "open",
						["h"] = "close_node",
						["s"] = "open_vsplit",
					},
				},
				filesystem = {
					filtered_items = {
						hide_dotfiles = false,
						hide_hidden = false,
						hide_by_name = { ".git", ".DS_Store", "thumbs.db" },
					},
					follow_current_file = { enabled = true, leave_dirs_open = true },
					use_libuv_file_watcher = true,
				},
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
		{
			"nvim-telescope/telescope.nvim",
			tag = "0.1.8",
			dependencies = {
				"nvim-lua/plenary.nvim",
				{ "nvim-telescope/telescope-fzf-native.nvim", build = "make" },
			},
		},
		{
			"numToStr/Comment.nvim",
			opts = { padding = true },
		},
		{ "akinsho/toggleterm.nvim", version = "*", config = true },
		{ "lewis6991/gitsigns.nvim", opts = {} },
		{ "lukas-reineke/indent-blankline.nvim", main = "ibl", opts = {} },
		-- Auto pairs
		{
			"windwp/nvim-autopairs",
			event = "InsertEnter",
			opts = {},
			config = function()
				-- Integration with nvim-cmp
				local cmp_autopairs = require("nvim-autopairs.completion.cmp")
				local cmp = require("cmp")
				cmp.event:on("confirm_done", cmp_autopairs.on_confirm_done())
			end,
		},
		{ "folke/which-key.nvim", opts = {} },
		{
			"romgrk/barbar.nvim",
			dependencies = {
				"lewis6991/gitsigns.nvim", -- OPTIONAL: for git status
				"nvim-tree/nvim-web-devicons", -- OPTIONAL: for file icons
			},
			init = function()
				vim.g.barbar_auto_setup = false
			end,
			opts = {
				-- lazy.nvim will automatically call setup for you. put your options here, anything missing will use the default:
				animation = true,
				tabpages = true,
				clickable = true,
			},
			version = "^1.0.0", -- optional: only update when a new 1.x version is released
		},
		{
			"nvim-pack/nvim-spectre",
			dependencies = { "nvim-lua/plenary.nvim" },
			config = function()
				require("spectre").setup({
					highlight = {
						ui = "String",
						search = "DiffChange",
						replace = "DiffDelete",
					},
				})
				vim.keymap.set(
					"n",
					"<leader>S",
					'<cmd>lua require("spectre").toggle()<CR>',
					{ desc = "Toggle Spectre" }
				)
				vim.keymap.set(
					"n",
					"<leader>sw",
					'<cmd>lua require("spectre").open_visual({select_word=true})<CR>',
					{ desc = "Search current word" }
				)
				vim.keymap.set(
					"v",
					"<leader>sw",
					'<esc><cmd>lua require("spectre").open_visual()<CR>',
					{ desc = "Search current selection" }
				)
			end,
		},
	},
})

vim.g.suda_smart_edit = 1
vim.cmd([[colorscheme tokyonight-moon]])

require("telescope").setup({
	pickers = {
		find_files = { hidden = true },
	},
})

require("nvim-treesitter.configs").setup({
	ensure_installed = {
		"lua",
		"vim",
		"vimdoc",
		"go",
		"gomod",
		"gosum",
		"cpp",
		"css",
		"html",
		"csv",
		"dockerfile",
		"gitignore",
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
		"diff",
		"git_config",
		"git_rebase",
		"gitattributes",
		"gitcommit",
		"java",
		"javascript",
		"json5",
		"proto",
		"regex",
		"ssh_config",
		"toml",
		"jinja",
	},
	sync_install = true,
	auto_install = true,
	highlight = { enable = true },
})

local capabilities = require("cmp_nvim_lsp").default_capabilities()

require("lspconfig").gopls.setup({
	capabilities = capabilities,
})
require("lspconfig").ruff.setup({
	capabilities = capabilities,
})

require("conform").setup({
	formatters = {
		yamlfmt = { prepend_args = { "-formatter", "max_line_length=240", "retain_line_breaks=true" } },
		taplo = { args = { "format", "--option", "indent_tables=true", "-" } },
		shfmt = { prepend_args = { "--indent", "4" } },
		prettier = { prepend_args = { "--print-width", "120", "--tab-width", "4", "--bracket-same-line" } },
	},
	formatters_by_ft = {
		["*"] = { "trim_whitespace" },
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
vim.keymap.set("n", "<F3>", "<cmd>Trouble diagnostics toggle focus=false filter.buf=0<CR>")
