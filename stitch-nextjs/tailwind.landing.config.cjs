// Extracted verbatim from the approved Stitch landing page's inline `tailwind.config` (CDN play build with plugins=forms,container-queries).
module.exports = {
  content: ["./src/landing/landing.body.html", "./public/landing/landing-scene.js"],
  ...{
      theme: {
        extend: {
          fontFamily: {
            sans: ['"Hanken Grotesk"', '"Manrope"', 'sans-serif'],
            mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
          },
          colors: {
            brand: {
              graphite: '#101820',
              navy: '#1e293b',
              slate: '#25313B',
              alloy: '#87949D',
              ivory: '#F5F3EE',
              warmwhite: '#E7E9E6',
              bronze: '#C18A54',
              cyan: '#0284C7',
              electric: '#0ea5e9',
              cyanlight: '#E0F2FE',
              verified: '#0284C7'
            }
          },
          keyframes: {
            pulseGlow: {
              '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
              '50%': { opacity: '0.9', transform: 'scale(1.08)' }
            },
            radarSweep: {
              '0%': { transform: 'rotate(0deg)' },
              '100%': { transform: 'rotate(360deg)' }
            },
            floatSlow: {
              '0%, 100%': { transform: 'translateY(0px)' },
              '50%': { transform: 'translateY(-6px)' }
            },
            flowDash: {
              to: { strokeDashoffset: '-24' }
            }
          },
          animation: {
            'pulse-glow': 'pulseGlow 3s ease-in-out infinite',
            'radar': 'radarSweep 8s linear infinite',
            'float-slow': 'floatSlow 5s ease-in-out infinite',
            'flow-dash': 'flowDash 1.2s linear infinite'
          }
        }
      }
    },
};
module.exports.plugins = [require("@tailwindcss/forms"), require("@tailwindcss/container-queries")];
