export const CAPTION_LOOKS = [
    { id: 'default', label: 'Default', font_name: 'Anton', font_size: 44, effect: 'pop', highlight_color: '#FFE500', border_width: 4, uppercase: true, max_chars: 16, base_opacity: 1, reveal: false, shadow: 0 },
    { id: 'hormozi', label: 'Hormozi', font_name: 'Montserrat ExtraBold', font_size: 44, effect: 'pop', highlight_color: '#FFE500', border_width: 4, uppercase: true, max_chars: 9, base_opacity: 1, reveal: true, shadow: 2 },
    { id: 'pill', label: 'Pill', font_name: 'Montserrat ExtraBold', font_size: 44, effect: 'highlight', highlight_color: '#7C3AED', border_width: 3, uppercase: true, max_chars: 9, base_opacity: 1, reveal: false, shadow: 0 },
    { id: 'lime', label: 'Lime box', font_name: 'Montserrat ExtraBold', font_size: 44, effect: 'highlight', highlight_color: '#A3FF12', border_width: 3, uppercase: true, max_chars: 9, base_opacity: 1, reveal: false, shadow: 0 },
    { id: 'oneword', label: 'One word', font_name: 'Anton', font_size: 70, effect: 'pop', highlight_color: '#FFFFFF', border_width: 5, uppercase: true, max_chars: 1, base_opacity: 1, reveal: false, shadow: 0 },
    { id: 'clean', label: 'Clean', font_name: 'Montserrat ExtraBold', font_size: 34, effect: 'none', highlight_color: '#FFFFFF', border_width: 0, uppercase: false, max_chars: 12, base_opacity: 0.7, reveal: false, shadow: 2 },
];

export const DEFAULT_CAPTION_STYLE = {
    preset: 'default', position: 'bottom', font_color: '#FFFFFF', border_color: '#000000',
    bg_color: '#000000', bg_opacity: 0, max_duration: 1.4,
    ...(({ id: _id, label: _label, ...fields }) => fields)(CAPTION_LOOKS[0]),
};

