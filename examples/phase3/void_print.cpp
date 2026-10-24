#include <iostream>
using namespace std;

void print_val(int x) {
    cout << "val=" << x << endl;
}

int main() {
    print_val(42);
    print_val(99);
    return 0;
}
