% design_filter.m
% Designs the receiver's bandpass filter and writes firmware/filter_coeffs.h
% for the Arduino. Needs the Signal Processing Toolbox.
%
% How to use:
%   1. Set f0 below to the transmitter frequency you measured.
%   2. Run this script using its full path; paths are relative to this file.
%   3. Use the header only with the matching alternative receiver (not yet provided).
%      Do not replace the active ESP32 receiver's filters with these coefficients.
%
% Prefer the filterDesigner GUI? Design it there, then File > Export > Workspace,
% export as SOS and G, and run:  write_coeffs_header(SOS, G, fs, 'filterDesigner export')

clear; clc;

% Resolve the companion writer even when MATLAB was started elsewhere.
here = fileparts(mfilename('fullpath'));
addpath(here);

%% ---- Settings (edit these) ----
f0      = 500;    % transmitter frequency you measured (Hz)  <-- PLACEHOLDER, replace
fs      = 3000;   % Arduino sample rate (Hz), must match what the Arduino can keep up with
bw      = 100;    % passband width (Hz): narrower = more selective but slower to react
order   = 2;      % Butterworth order (bandpass doubles it: order 2 -> 2 biquad sections)
rejects = [120];  % interferer frequencies to check, e.g. [120 650 1000]

%% ---- Aliasing check ----
target = f0;
if f0 >= fs/2
    target = mod(f0, fs);
    if target > fs/2, target = fs - target; end
    warning(['%g Hz is above Nyquist (%g Hz). It will show up at %.1f Hz after sampling. ' ...
             'Designing for that, but raising fs is the better fix.'], f0, fs/2, target);
end
if fs/target < 4
    fprintf('Note: only %.1f samples per cycle. The spec suggests about 10. Consider a higher fs.\n', fs/target);
end

lo = target - bw/2;
hi = target + bw/2;
if lo <= 0 || hi >= fs/2
    error('Passband %.0f-%.0f Hz does not fit between 0 and Nyquist (%.0f Hz). Change bw, f0 or fs.', lo, hi, fs/2);
end

%% ---- Design ----
[z, p, k] = butter(order, [lo hi] / (fs/2), 'bandpass');
[sos, g]  = zp2sos(z, p, k);

%% ---- Write the Arduino header ----
write_coeffs_header(sos, g, fs, sprintf('Butterworth bandpass: center %g Hz, width %g Hz, order %d', target, bw, order));

%% ---- Checks ----
sosArduino = sos; sosArduino(1,1:3) = sosArduino(1,1:3) * g;   % what the Arduino runs
sos32 = double(single(sosArduino));                              % Arduino uses 32-bit floats
poles = [];
for i = 1:size(sos32,1)
    poles = [poles; roots(sos32(i,4:6))]; %#ok<AGROW>
end
fprintf('Max pole radius (float32): %.5f  (must be < 1)\n\n', max(abs(poles)));

gainAt = @(f) 20*log10(abs(freqz(sos32, [f f], fs)));
gt = gainAt(target);
fprintf('Gain at %.0f Hz (target): %6.1f dB\n', target, gt(1));
for f = rejects
    fa = mod(f, fs); if fa > fs/2, fa = fs - fa; end
    gr = gainAt(fa);
    fprintf('Gain at %.0f Hz:          %6.1f dB\n', f, gr(1));
end

%% ---- Plot: response + simulated beam break ----
[h, w] = freqz(sos32, 4096, fs);
t  = (0:round(fs*1)-1)' / fs;
tx = 0.3 * (square(2*pi*target*t) + 1) / 2;
tx(t > 0.5) = 0;                                   % beam blocked halfway through
x  = tx + 0.02*randn(size(t));
for f = rejects, x = x + 0.5*sin(2*pi*f*t); end
y  = sosfilt(sos32, x - mean(x));

figure('Name', 'Filter design', 'Position', [100 100 800 800]);
subplot(3,1,1);
plot(w, 20*log10(max(abs(h), 1e-12))); hold on; grid on;
xline(target, 'g--', 'target');
for f = rejects, xline(f, 'r:', sprintf('%g Hz', f)); end
ylim([-80 5]); xlabel('Frequency (Hz)'); ylabel('Gain (dB)'); title('Filter response');
subplot(3,1,2); plot(t, x); grid on;
xlabel('Time (s)'); title('Simulated input (beam + interferers, beam blocked at 0.5 s)');
subplot(3,1,3); plot(t, y); grid on;
xlabel('Time (s)'); title('Filter output');

docs = fullfile(here, '..', 'docs');
if ~exist(docs, 'dir'), mkdir(docs); end
saveas(gcf, fullfile(docs, 'filter_response.png'));
fprintf('\nSaved docs/filter_response.png\n');
