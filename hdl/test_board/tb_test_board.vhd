-- Banco de pruebas: con DIV_BITS = 3 el contador avanza cada 8 ciclos.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_test_board is
end entity tb_test_board;

architecture sim of tb_test_board is
  signal clk : std_logic := '0';
  signal sw  : std_logic_vector(7 downto 0) := (others => '0');
  signal led : std_logic_vector(15 downto 0);
begin

  dut : entity work.test_board
    generic map (DIV_BITS => 3)
    port map (CLK100MHZ => clk, SW => sw, LED => led);

  clk <= not clk after 5 ns;

  process
  begin
    -- Tras 8 ciclos (el divisor vale 7 en el 8.º flanco) el contador pasa a 1.
    wait for 8 * 10 ns + 1 ns;
    assert unsigned(led(7 downto 0)) = 1
      report "El contador debía valer 1 tras 8 ciclos" severity failure;
    wait for 8 * 10 ns;
    assert unsigned(led(7 downto 0)) = 2
      report "El contador debía valer 2 tras 16 ciclos" severity failure;

    -- Los interruptores se reflejan en los LED superiores.
    sw <= "10100101";
    wait for 1 ns;
    assert led(15 downto 8) = "10100101"
      report "Los LED[15:8] no reflejan los interruptores" severity failure;

    report "OK: banco de pruebas superado";
    wait;
  end process;

end architecture sim;
