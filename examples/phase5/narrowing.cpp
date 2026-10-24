#include <iostream>
using namespace std;

int main() {
    long long big1 = 4294967296;
    int narrow1 = big1;
    long long big2 = 2147483648;
    int narrow2 = big2;
    cout << narrow1 << endl;
    cout << narrow2 << endl;
    return 0;
}
