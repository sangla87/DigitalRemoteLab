-- Banco de pruebas de clock_gen con semiperiodos pequeños (en ciclos de reloj de 10 ns):
-- 1 kHz -> 4, 1 Hz -> 20, 10 Hz -> 8; manual con salida a '1' durante 6 ciclos.

library ieee;
use ieee.std_logic_1164.all;

entity tb_clock_gen is
end entity tb_clock_gen;

architecture sim of tb_clock_gen is
  constant T : time := 10 ns;
  signal clk     : std_logic := '0';
  signal mode    : std_logic_vector(1 downto 0) := "00";
  signal pulse   : std_logic := '0';
  signal clk_out : std_logic;
  signal rising  : natural := 0;
  signal running : boolean := true;
begin

  dut : entity work.clock_gen
    generic map (HALF_1KHZ => 4, HALF_1HZ => 20, HALF_10HZ => 8, MANUAL_HOLD => 6)
    port map (clk => clk, mode => mode, pulse => pulse, clk_out => clk_out);

  clk <= not clk after T / 2 when running else clk;

  process (clk_out)
  begin
    if rising_edge(clk_out) then
      rising <= rising + 1;
    end if;
  end process;

  stim : process
    -- Mide el periodo entre dos flancos de subida consecutivos y lo compara con el esperado.
    procedure check_period(expected : time; what : string) is
      variable t0 : time;
    begin
      wait until rising_edge(clk_out);
      t0 := now;
      wait until rising_edge(clk_out);
      assert now - t0 = expected
        report what & ": periodo " & time'image(now - t0) & ", esperado " & time'image(expected)
        severity failure;
    end procedure;

    variable before : natural;
  begin
    mode <= "00";
    wait for 4 * T;
    check_period(8 * T, "1 kHz");
    check_period(8 * T, "1 kHz (segundo periodo)");

    mode <= "01";
    wait for 4 * T;
    check_period(40 * T, "1 Hz");

    mode <= "10";
    wait for 4 * T;
    check_period(16 * T, "10 Hz");

    -- Modo manual: sin pulsos no hay flancos; cada pulso da exactamente uno.
    mode <= "11";
    wait for 10 * T;
    before := rising;
    wait for 40 * T;
    assert rising = before report "modo manual: flancos sin pulso" severity failure;

    pulse <= '1';
    wait for 30 * T;               -- pulso largo: debe contar como uno solo
    pulse <= '0';
    wait for 20 * T;
    assert rising = before + 1 report "modo manual: un pulso debía dar un flanco" severity failure;

    pulse <= '1';
    wait for 3 * T;
    pulse <= '0';
    wait for 30 * T;
    assert rising = before + 2 report "modo manual: el segundo pulso no dio un flanco" severity failure;

    -- Volver a un modo automático no debe dejar la salida a '1'.
    mode <= "00";
    wait for 2 * T;
    assert clk_out = '0' report "tras cambiar de modo la salida debía estar a '0'" severity failure;

    report "banco de pruebas superado";
    running <= false;
    wait;
  end process;

end architecture sim;
