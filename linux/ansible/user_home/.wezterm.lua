-- Pull in the wezterm API
local wezterm = require 'wezterm'

-- This will hold the configuration.
local config = wezterm.config_builder()

-- This is where you actually apply your config choices

-- For example, changing the color scheme:
config.color_scheme = 'tokyonight_night'

config.window_frame = {

  font = wezterm.font_with_fallback{'MesloLGS Nerd Font Mono', 'MesloLGS NF', 'JetBrainsMono Nerd Font Mono', 'JetBrains Mono'},
  
  font_size = 11.0,
  
}

config.window_decorations = "INTEGRATED_BUTTONS|RESIZE"
config.use_fancy_tab_bar = true
config.font = wezterm.font_with_fallback{'MesloLGS Nerd Font Mono', 'MesloLGS NF', 'JetBrainsMono Nerd Font Mono', 'JetBrains Mono'}
config.enable_scroll_bar = true
config.window_background_opacity = 0.975

config.window_padding = {
  left = '1cell',
  right = '1cell',
  top = '0.5cell',
  bottom = '0.5cell',
}

config.harfbuzz_features = { 'calt=1', 'clig=1', 'liga=1' }

-- and finally, return the configuration to wezterm
return config
