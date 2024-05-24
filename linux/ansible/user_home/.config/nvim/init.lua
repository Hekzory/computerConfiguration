vim.opt.number = true
vim.opt.mouse = 'a'
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4

vim.keymap.set({'n', 'x'}, 'gy', '"+y')
vim.keymap.set({'n', 'x'}, 'gp', '"+p')

local lazy = {}

function lazy.install(path)
	if not (vim.uv or vim.loop).fs_stat(path) then
		print('Installing lazy.nvim....')
		vim.fn.system({
			'git',
	  		'clone',
			'--filter=blob:none',
			'https://github.com/folke/lazy.nvim.git',
			'--branch=stable', -- latest stable release
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

	require('lazy').setup(plugins, lazy.opts)
	vim.g.plugins_ready = true
end

vim.g.suda_smart_edit = 1

lazy.path = vim.fn.stdpath('data') .. '/lazy/lazy.nvim'
lazy.opts = {}

lazy.setup({
	{"folke/tokyonight.nvim", lazy = false, priority = 1000 },
	{
    	'nvim-lualine/lualine.nvim',
    	dependencies = { 'nvim-tree/nvim-web-devicons' }
	},
	{
		"ms-jpq/coq_nvim",
		branch = 'coq',
		dependencies = { "ms-jpq/coq.artifacts" },
	},
	{
		"lambdalisue/vim-suda",
	},
	{
		"nvim-treesitter/nvim-treesitter", 
		build = ":TSUpdate"
	},
	{
    	"nvim-neo-tree/neo-tree.nvim",
    	branch = "v3.x",
    	dependencies = {
      		"nvim-lua/plenary.nvim",
      		"nvim-tree/nvim-web-devicons", -- not strictly required, but recommended
      		"MunifTanjim/nui.nvim",
      		-- "3rd/image.nvim", -- Optional image support in preview window: See `# Preview Mode` for more information
    	},
	},
})

vim.opt.termguicolors = true
vim.cmd[[colorscheme tokyonight-night]]

require('lualine').setup({
	options = { theme = 'tokyonight', },
})

vim.cmd[[COQnow --shut-up]]

require('nvim-treesitter.configs').setup({
	ensure_installed = { "c", "lua", "vim", "vimdoc", "query", "go", "cpp", "css", "html", "csv", "dockerfile", "gitignore", "html", "bash", "json", "make", "python", "rust", "sql", "udev", "yaml", "xml" },
	sync_install = true,
	auto_install = true,
	highlight = {
		enable = true,
	}
})
