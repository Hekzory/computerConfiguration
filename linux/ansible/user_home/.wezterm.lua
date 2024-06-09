-- Pull in the wezterm API
local wezterm = require 'wezterm'
local mux = wezterm.mux

-- This will hold the configuration.
local config = wezterm.config_builder()

-- This is where you actually apply your config choices

-- For example, changing the color scheme:
config.color_scheme = 'tokyonight_night'

config.term = "wezterm"

config.window_frame = {
	font = wezterm.font_with_fallback{'MesloLGS NF', 'MesloLGS Nerd Font Mono', 'JetBrainsMono Nerd Font Mono', 'JetBrains Mono'},
	font_size = 11.0,
}

config.window_decorations = "INTEGRATED_BUTTONS|RESIZE"
config.integrated_title_button_color = "Auto"
config.use_fancy_tab_bar = true
config.font = wezterm.font_with_fallback{'MesloLGS NF', 'MesloLGS Nerd Font Mono', 'JetBrainsMono Nerd Font Mono', 'JetBrains Mono'}
config.enable_scroll_bar = true
config.window_background_opacity = 0.975
config.font_size = 11.0
config.use_resize_increments = true

config.window_padding = {
	left = '1cell',
	right = '1cell',
	top = '0.5cell',
	bottom = '0.5cell',
}

config.harfbuzz_features = { 'calt=1', 'clig=1', 'liga=1' }

config.prefer_egl=true

config.front_end="WebGpu"
config.webgpu_power_preference = "HighPerformance"

-- Experimental undocumented features to improve perceived performance
-- default delay is 3ms
config.mux_output_parser_coalesce_delay_ms = 1
-- default size is 256
config.glyph_cache_image_cache_size = 512
-- default size is 1024
config.shape_cache_size = 2048
config.line_state_cache_size = 2048
config.line_quad_cache_size = 2048
config.line_to_ele_shape_cache_size = 2048
-- default is 10 fps for animations
config.animation_fps = 60
-- default is 60
config.max_fps = 165

-- and finally, return the configuration to wezterm
return config
