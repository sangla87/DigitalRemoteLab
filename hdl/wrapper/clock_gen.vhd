-- Generador del reloj que recibe el diseño del alumno.
--
-- Parte del reloj de 100 MHz de la placa y entrega, sin glitches (la salida sale directamente de
-- un registro, y opcionalmente pasa por un BUFG), uno de estos relojes:
--
--   mode = "00"  1 kHz   (multiplexado de displays)
--   mode = "01"  1 Hz
--   mode = "10"  10 Hz
--   mode = "11"  manual: un único flanco de subida por cada pulso de la entrada `pulse`
--
-- Los semiperiodos son genéricos para poder simular con valores pequeños. Al cambiar de modo se
-- reinicia el contador y la salida baja a '0' (no se genera ningún flanco de subida espurio).

library ieee;
use ieee.std_logic_1164.all;

entity clock_gen is
  generic (
    HALF_1KHZ   : positive := 50_000;      -- ciclos de 100 MHz por semiperiodo
    HALF_1HZ    : positive := 50_000_000;
    HALF_10HZ   : positive := 5_000_000;
    MANUAL_HOLD : positive := 5_000;       -- ciclos que la salida se mantiene a '1' en modo manual
    USE_BUFG    : boolean  := false        -- true al sintetizar con Vivado
  );
  port (
    clk     : in  std_logic;
    mode    : in  std_logic_vector(1 downto 0);
    pulse   : in  std_logic;               -- botón virtual (asíncrono: se sincroniza aquí)
    clk_out : out std_logic
  );
end entity clock_gen;

architecture rtl of clock_gen is
  constant MODE_1KHZ   : std_logic_vector(1 downto 0) := "00";
  constant MODE_1HZ    : std_logic_vector(1 downto 0) := "01";
  constant MODE_10HZ   : std_logic_vector(1 downto 0) := "10";

  signal mode_q : std_logic_vector(1 downto 0) := "00";
  signal sync   : std_logic_vector(1 downto 0) := "00";
  signal prev   : std_logic := '0';
  signal cnt    : integer range 0 to HALF_1HZ := 0;
  signal hold   : integer range 0 to MANUAL_HOLD := 0;
  signal tog    : std_logic := '0';

  component BUFG
    port (I : in std_logic; O : out std_logic);
  end component;
begin

  process (clk)
    variable half : integer range 1 to HALF_1HZ;
  begin
    if rising_edge(clk) then
      mode_q <= mode;
      sync   <= sync(0) & pulse;
      prev   <= sync(1);

      case mode is
        when MODE_1KHZ => half := HALF_1KHZ;
        when MODE_1HZ  => half := HALF_1HZ;
        when others    => half := HALF_10HZ;
      end case;

      if mode /= mode_q then
        cnt  <= 0;
        hold <= 0;
        tog  <= '0';
      elsif mode = "11" then
        if hold > 0 then
          hold <= hold - 1;
          if hold = 1 then
            tog <= '0';
          end if;
        elsif sync(1) = '1' and prev = '0' then
          tog  <= '1';
          hold <= MANUAL_HOLD;
        end if;
      else
        if cnt = half - 1 then
          cnt <= 0;
          tog <= not tog;
        else
          cnt <= cnt + 1;
        end if;
      end if;
    end if;
  end process;

  use_bufg_gen : if USE_BUFG generate
    bufg_i : BUFG port map (I => tog, O => clk_out);
  end generate;

  no_bufg_gen : if not USE_BUFG generate
    clk_out <= tog;
  end generate;

end architecture rtl;
