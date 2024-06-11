-- Pull in the wezterm API
local wezterm = require 'wezterm'

-- This will hold the configuration.
local config = wezterm.config_builder()

-- Appearance settings
config.color_scheme = 'tokyonight_night'
if wezterm.target_triple == "x86_64-unknown-linux-gnu" then
  config.default_prog = { '/bin/zsh' }
  config.font = wezterm.font_with_fallback{
    'MesloLGS NF',
    'JetBrainsMono Nerd Font Mono', 
    'JetBrains Mono'
  }
else
  config.default_prog = { 'pwsh.exe', '-NoLogo' }
  config.font = wezterm.font_with_fallback{
    'MesloLGS Nerd Font Mono', 
    'JetBrainsMono Nerd Font Mono', 
    'JetBrains Mono'
  }
end
config.font_size = 11.0
config.window_frame = {
  font = config.font,
  font_size = config.font_size,
}
config.window_decorations = "INTEGRATED_BUTTONS|RESIZE"
config.integrated_title_button_color = "Auto"
config.use_fancy_tab_bar = true
config.window_background_opacity = 0.975
config.enable_scroll_bar = true
config.use_resize_increments = true

-- Window padding
config.window_padding = {
  left = '1cell',
  right = '1cell',
  top = '0.5cell',
  bottom = '0.5cell',
}

-- Font features
config.harfbuzz_features = { 'calt=1', 'clig=1', 'liga=1' }

-- Backend settings
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

-- Set terminal type for better integration
config.term = "wezterm"

-- and finally, return the configuration to wezterm
return config
