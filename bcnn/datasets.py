import os
import os.path
from typing import Any, Callable, Optional, Tuple, List
from PIL import Image
import pickle
import numpy as np
import torch
import torchvision.transforms as T
from torch.utils.data import Dataset
from torchvision.datasets import EMNIST
from torchvision.datasets.vision import VisionDataset
from torchvision.datasets.utils import check_integrity, download_and_extract_archive, download_url, verify_str_arg

# Add these helper classes before your DigitsVsLetters class
class TransposeTransform:
    """Callable transform to fix EMNIST transpose"""
    def __call__(self, img: Image.Image) -> Image.Image:
        return img.transpose(Image.Transpose.TRANSPOSE)

class RepeatChannels:
    """Callable transform to repeat grayscale to 3 channels"""
    def __call__(self, tensor: torch.Tensor) -> torch.Tensor:
        return tensor.repeat(3, 1, 1)


class DigitsVsLetters(Dataset[tuple[torch.Tensor, torch.FloatTensor]]):
    """
    Binary classification dataset: Digits (0-9) vs Letters (A-Z, a-z)
    """
    def __init__(self, train: bool = True, download: bool = False, transform: Callable[[torch.Tensor], torch.Tensor] | None = None) -> None:
        self.train = train
        
        self.emnist = EMNIST(
            root=os.path.join("datasets", "emnist"),
            split='byclass',
            train=train,
            download=download,
            transform=None
        )
        
        targets = self.emnist.targets
        if isinstance(targets, torch.Tensor):
            targets = targets.numpy()
        
        self.digit_indices = np.where(targets < 10)[0].tolist()
        self.letter_indices = np.where(targets >= 10)[0].tolist()
        
        min_len = min(len(self.digit_indices), len(self.letter_indices))
        self.digit_indices = self.digit_indices[:min_len]
        self.letter_indices = self.letter_indices[:min_len]
        self.min_len = min_len
        
        # tqdm.write(f"DigitsVsLetters ({'train' if train else 'test'}): {min_len} digits, {min_len} letters")
        
        if train:
            self.transform = T.Compose([
                TransposeTransform(),  # Replace lambda
                T.RandomRotation(10),
                T.Resize((16, 16)),
                T.ToTensor(),
                T.Normalize((0.1307,), (0.3081,)),
                # RepeatChannels()  # Replace lambda
            ])
        else:
            self.transform = T.Compose([
                TransposeTransform(),  # Replace lambda
                T.Resize((16, 16)),
                T.ToTensor(),
                T.Normalize((0.1307,), (0.3081,)),
                # RepeatChannels()  # Replace lambda
            ])
    
    def __len__(self) -> int:
        return 2 * self.min_len
    
    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.FloatTensor]:
        half_len = self.min_len
        
        if idx < half_len:
            actual_idx = self.digit_indices[idx]
            img, _ = self.emnist[actual_idx]
            data = self.transform(img)
            return data, torch.FloatTensor([1, 0])
        else:
            actual_idx = self.letter_indices[idx - half_len]
            img, _ = self.emnist[actual_idx]
            data = self.transform(img)
            return data, torch.FloatTensor([0, 1])


class CIFAR10(VisionDataset):
    """`CIFAR10 <https://www.cs.toronto.edu/~kriz/cifar.html>`_ Dataset.

    Args:
        root (string): Root directory of dataset where directory
            ``cifar-10-batches-py`` exists or will be saved to if download is set to True.
        train (bool, optional): If True, creates dataset from training set, otherwise
            creates from test set.
        transform (callable, optional): A function/transform that takes in an PIL image
            and returns a transformed version. E.g, ``transforms.RandomCrop``
        target_transform (callable, optional): A function/transform that takes in the
            target and transforms it.
        download (bool, optional): If true, downloads the dataset from the internet and
            puts it in root directory. If dataset is already downloaded, it is not
            downloaded again.

    """
    base_folder = 'cifar-10-batches-py'
    url = "https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz"
    filename = "cifar-10-python.tar.gz"
    tgz_md5 = 'c58f30108f718f92721af3b95e74349a'
    train_list = [
        ['data_batch_1', 'c99cafc152244af753f735de768cd75f'],
        ['data_batch_2', 'd4bba439e000b95fd0a9bffe97cbabec'],
        ['data_batch_3', '54ebc095f3ab1f0389bbae665268c751'],
        ['data_batch_4', '634d18415352ddfa80567beed471001a'],
        ['data_batch_5', '482c414d41f54cd18b22e5b47cb7c3cb'],
    ]

    test_list = [
        ['test_batch', '40351d587109b95175f43aff81a1287e'],
    ]
    meta = {
        'filename': 'batches.meta',
        'key': 'label_names',
        'md5': '5ff9c542aee3614f3951f8cda6e48888',
    }

    def __init__(
            self,
            root: str,
            train: bool = True,
            transform: Optional[Callable] = None,
            target_transform: Optional[Callable] = None,
            download: bool = False,
    ) -> None:

        super(CIFAR10, self).__init__(root, transform=transform,
                                      target_transform=target_transform)

        self.train = train  # training set or test set

        if download:
            self.download()

        if not self._check_integrity():
            raise RuntimeError('Dataset not found or corrupted.' +
                               ' You can use download=True to download it')

        if self.train:
            downloaded_list = self.train_list
        else:
            downloaded_list = self.test_list

        self.data: Any = []
        self.targets = []

        # now load the picked numpy arrays
        for file_name, checksum in downloaded_list:
            file_path = os.path.join(self.root, self.base_folder, file_name)
            with open(file_path, 'rb') as f:
                entry = pickle.load(f, encoding='latin1')
                self.data.append(entry['data'])
                if 'labels' in entry:
                    self.targets.extend(entry['labels'])
                else:
                    self.targets.extend(entry['fine_labels'])

        self.data = np.vstack(self.data).reshape(-1, 3, 32, 32)
        self.data = self.data.transpose((0, 2, 3, 1))  # convert to HWC

        self._load_meta()

    def _load_meta(self) -> None:
        path = os.path.join(self.root, self.base_folder, self.meta['filename'])
        if not check_integrity(path, self.meta['md5']):
            raise RuntimeError('Dataset metadata file not found or corrupted.' +
                               ' You can use download=True to download it')
        with open(path, 'rb') as infile:
            data = pickle.load(infile, encoding='latin1')
            self.classes = data[self.meta['key']]
        self.class_to_idx = {_class: i for i, _class in enumerate(self.classes)}

    def __getitem__(self, index: int) -> Tuple[Any, Any]:
        """
        Args:
            index (int): Index

        Returns:
            tuple: (image, target) where target is index of the target class.
        """
        img, target = self.data[index], self.targets[index]

        # doing this so that it is consistent with all other datasets
        # to return a PIL Image
        img = Image.fromarray(img)

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target

    def __len__(self) -> int:
        return len(self.data)

    def _check_integrity(self) -> bool:
        root = self.root
        for fentry in (self.train_list + self.test_list):
            filename, md5 = fentry[0], fentry[1]
            fpath = os.path.join(root, self.base_folder, filename)
            if not check_integrity(fpath, md5):
                return False
        return True

    def download(self) -> None:
        if self._check_integrity():
            print('Files already downloaded and verified')
            return
        download_and_extract_archive(self.url, self.root, filename=self.filename, md5=self.tgz_md5)

    def extra_repr(self) -> str:
        return "Split: {}".format("Train" if self.train is True else "Test")
    

class _LFW(VisionDataset):

    base_folder = 'lfw-py'
    download_url_prefix = "http://vis-www.cs.umass.edu/lfw/"

    file_dict = {
        'original': ("lfw", "lfw.tgz", "a17d05bd522c52d84eca14327a23d494"),
        'funneled': ("lfw_funneled", "lfw-funneled.tgz", "1b42dfed7d15c9b2dd63d5e5840c86ad"),
        'deepfunneled': ("lfw-deepfunneled", "lfw-deepfunneled.tgz", "68331da3eb755a505a502b5aacb3c201")
    }
    checksums = {
        'pairs.txt': '9f1ba174e4e1c508ff7cdf10ac338a7d',
        'pairsDevTest.txt': '5132f7440eb68cf58910c8a45a2ac10b',
        'pairsDevTrain.txt': '4f27cbf15b2da4a85c1907eb4181ad21',
        'people.txt': '450f0863dd89e85e73936a6d71a3474b',
        'peopleDevTest.txt': 'e4bf5be0a43b5dcd9dc5ccfcb8fb19c5',
        'peopleDevTrain.txt': '54eaac34beb6d042ed3a7d883e247a21',
        'lfw-names.txt': 'a6d0a479bd074669f656265a6e693f6d'
    }
    annot_file = {'10fold': '', 'train': 'DevTrain', 'test': 'DevTest'}
    names = "lfw-names.txt"

    def __init__(
        self,
        root: str,
        split: str,
        image_set: str,
        view: str,
        transform: Optional[Callable] = None,
        target_transform: Optional[Callable] = None,
        download: bool = False,
    ):
        super(_LFW, self).__init__(os.path.join(root, self.base_folder),
                                   transform=transform, target_transform=target_transform)

        self.image_set = verify_str_arg(image_set.lower(), 'image_set', self.file_dict.keys())
        images_dir, self.filename, self.md5 = self.file_dict[self.image_set]

        self.view = verify_str_arg(view.lower(), 'view', ['people', 'pairs'])
        self.split = verify_str_arg(split.lower(), 'split', ['10fold', 'train', 'test'])
        self.labels_file = f"{self.view}{self.annot_file[self.split]}.txt"
        self.data: List[Any] = []

        if download:
            self.download()

        if not self._check_integrity():
            raise RuntimeError('Dataset not found or corrupted.' +
                               ' You can use download=True to download it')

        self.images_dir = os.path.join(self.root, images_dir)

    def _loader(self, path: str) -> Image.Image:
        with open(path, 'rb') as f:
            img = Image.open(f)
            return img.convert('RGB')

    def _check_integrity(self):
        st1 = check_integrity(os.path.join(self.root, self.filename), self.md5)
        st2 = check_integrity(os.path.join(self.root, self.labels_file), self.checksums[self.labels_file])
        if not st1 or not st2:
            return False
        if self.view == "people":
            return check_integrity(os.path.join(self.root, self.names), self.checksums[self.names])
        return True

    def download(self):
        if self._check_integrity():
            print('Files already downloaded and verified')
            return
        url = f"{self.download_url_prefix}{self.filename}"
        download_and_extract_archive(url, self.root, filename=self.filename, md5=self.md5)
        download_url(f"{self.download_url_prefix}{self.labels_file}", self.root)
        if self.view == "people":
            download_url(f"{self.download_url_prefix}{self.names}", self.root)

    def _get_path(self, identity, no):
        return os.path.join(self.images_dir, identity, f"{identity}_{int(no):04d}.jpg")

    def extra_repr(self) -> str:
        return f"Alignment: {self.image_set}\nSplit: {self.split}"

    def __len__(self):
        return len(self.data)


class LFWPeople(_LFW):
    """`LFW <http://vis-www.cs.umass.edu/lfw/>`_ Dataset.

    Args:
        root (string): Root directory of dataset where directory
            ``lfw-py`` exists or will be saved to if download is set to True.
        split (string, optional): The image split to use. Can be one of ``train``, ``test``,
            ``10fold`` (default).
        image_set (str, optional): Type of image funneling to use, ``original``, ``funneled`` or
            ``deepfunneled``. Defaults to ``funneled``.
        transform (callable, optional): A function/transform that  takes in an PIL image
            and returns a transformed version. E.g, ``transforms.RandomRotation``
        target_transform (callable, optional): A function/transform that takes in the
            target and transforms it.
        download (bool, optional): If true, downloads the dataset from the internet and
            puts it in root directory. If dataset is already downloaded, it is not
            downloaded again.

    """

    def __init__(
        self,
        root: str,
        split: str = "10fold",
        image_set: str = "funneled",
        transform: Optional[Callable] = None,
        target_transform: Optional[Callable] = None,
        download: bool = False,
    ):
        super(LFWPeople, self).__init__(root, split, image_set, "people",
                                        transform, target_transform, download)

        self.class_to_idx = self._get_classes()
        self.data, self.targets = self._get_people()

    def _get_people(self):
        data, targets = [], []
        with open(os.path.join(self.root, self.labels_file), 'r') as f:
            lines = f.readlines()
            n_folds, s = (int(lines[0]), 1) if self.split == "10fold" else (1, 0)

            for fold in range(n_folds):
                n_lines = int(lines[s])
                people = [line.strip().split("\t") for line in lines[s + 1: s + n_lines + 1]]
                s += n_lines + 1
                for i, (identity, num_imgs) in enumerate(people):
                    for num in range(1, int(num_imgs) + 1):
                        img = self._get_path(identity, num)
                        data.append(img)
                        targets.append(self.class_to_idx[identity])

        return data, targets

    def _get_classes(self):
        with open(os.path.join(self.root, self.names), 'r') as f:
            lines = f.readlines()
            names = [line.strip().split()[0] for line in lines]
        class_to_idx = {name: i for i, name in enumerate(names)}
        return class_to_idx

    def __getitem__(self, index: int) -> Tuple[Any, Any]:
        """
        Args:
            index (int): Index

        Returns:
            tuple: Tuple (image, target) where target is the identity of the person.
        """
        img = self._loader(self.data[index])
        target = self.targets[index]

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target

    def extra_repr(self) -> str:
        return super().extra_repr() + "\nClasses (identities): {}".format(len(self.class_to_idx))


class FaceNotFace():
    def __init__(self, train:bool = False, download:bool = False, cifar_transform:Optional[Callable] = None, lfw_transform:Optional[Callable] = None, target_transform:Optional[Callable] = None):
        self.train = train
        if self.train:
            split = 'train'
            if cifar_transform is None:
                cifar_transform = T.Compose([T.RandomCrop(32, padding = 4),
                                             T.RandomHorizontalFlip(),
                                             T.Resize((16,16)),
                                             T.ToTensor(),
                                             T.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))])
        else:
            split = 'test'
            if cifar_transform is None:
                cifar_transform = T.Compose([T.Resize((16,16)),
                                             T.ToTensor(),
                                             T.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))])

        self.cifar10 = CIFAR10(os.path.join("datasets", "cifar10"), train = self.train, download=download, transform=cifar_transform, target_transform=target_transform)
        self.lfw = LFWPeople(os.path.join("datasets", "lfw"), split = split, image_set = 'funneled', download=download, transform=lfw_transform, target_transform=target_transform)
        self.t = T.Compose([
            T.ToTensor(),
            T.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
        ])

    def __len__(self):
        if len(self.cifar10) > len(self.lfw):
            return 2*len(self.lfw)
        else:
            return 2*len(self.cifar10)
    
    def __getitem__(self, idx):
        if idx < int(self.__len__()/2):
            data, _ = self.cifar10.__getitem__(idx)
            return data, torch.FloatTensor([1, 0])
        else:
            data, _ = self.lfw.__getitem__(idx-int(self.__len__()/2))
            data = data.crop((61,61,189,189))
            data = data.resize((16,16), resample=Image.BILINEAR)
            return self.t(data), torch.FloatTensor([0, 1])
        

class Binarize(object):
    '''
    Binarize a tensor between -1 and 1. 
    '''
    def __call__(self, sample):
        # normalize
        sample = (sample - sample.mean()) / sample.std()
        # binarize
        sample = sample.sign()
        return sample


class TranslatorDataGen():
    '''
    Generate binarized data for training the EODLA translator model. 
    '''
    
    def __init__(self,
                 train:bool = False, 
                 download:bool = False, 
                 dataset_size:int = 2800, 
                 image_size:int = 16, 
                 kernel_size:int = 3,
                 in_channels:int = 3):
        
        self.dataset_size = dataset_size
        self.image_size = image_size
        self.in_channels = in_channels
        self.kernel_size = kernel_size
        self.transform = T.Compose([
            T.Grayscale(num_output_channels=1),
            Binarize()
        ])
        # self.kernel_transform = T.Compose([
        #     T.RandomAffine(
        #         degrees=90,
        #         translate=(0.2, 0.2),
        #         interpolation=T.InterpolationMode.NEAREST,
        #     ),
        #     T.RandomResizedCrop(
        #         size=self.kernel_size, 
        #         scale=(0.333, 1.0),
        #         interpolation=T.InterpolationMode.NEAREST,
        #     ),
        # ])
        
        if download:
            self.make_kernels(dataset_size=self.dataset_size, kernel_size=self.kernel_size)
        
        if train:
            self.dvl = DigitsVsLetters(train=True, download=download)
            cifar_transform = T.Compose([T.RandomCrop(32, padding = 4),
                                        T.RandomHorizontalFlip(),
                                        T.Resize((16,16)),
                                        T.ToTensor(),
                                        T.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
                                        ])
            self.cifar10 = CIFAR10(os.path.join("datasets", "cifar10"), train = True, download=download, transform=cifar_transform)
            # self.fnf = FaceNotFace(train=True, download=download)
            # self.kernel = np.load(os.path.join("datasets", "translator_data", f"kernel_ints_{self.kernel_size}_train.pkl"), "rb")
        else:
            self.dvl = DigitsVsLetters(train=False, download=download)
            cifar_transform = T.Compose([T.Resize((16,16)),
                                        T.ToTensor(),
                                        T.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
                                        ])
            self.cifar10 = CIFAR10(os.path.join("datasets", "cifar10"), train = False, download=download, transform=cifar_transform)
            # self.fnf = FaceNotFace(train=False, download=download)
            # self.kernel = np.load(os.path.join("datasets", "translator_data", f"kernel_ints_{self.kernel_size}_test.pkl"), "rb")
        
    def __len__(self):
        return self.dataset_size
    
    def __getitem__(self, idx):
        if idx < int(self.dataset_size/2):
            data, label = self.cifar10.__getitem__(idx)
            label = torch.tensor([int(label), 1, idx], dtype=torch.float32)
        else:
            data, label = self.dvl.__getitem__(idx-int(self.dataset_size/2))
            label = torch.tensor([int(label.argmax().item()), 0, idx], dtype=torch.float32)
        
        data = self.transform(data)

        return data, label
        
    @staticmethod
    def make_kernels(dataset_size:int, kernel_size:int = 3, train_test_split:float = 0.7, val_split:float = 0.1):
        # generate ints
        rng = np.random.default_rng()
        kernel_ints = rng.choice(2 ** (6 ** 2), size=dataset_size, replace=False)
        
        # split data
        kernels_train = kernel_ints[:int(len(kernel_ints)*train_test_split)]
        kernels_val = kernel_ints[int(len(kernel_ints)*train_test_split):int(len(kernel_ints)*(train_test_split + val_split))]
        kernels_test = kernel_ints[int(len(kernel_ints)*(train_test_split + val_split)):]
        
        # save to file
        os.makedirs(os.path.join("datasets", "translator_data"), exist_ok=True)
        np.save(os.path.join("datasets", "translator_data", f"kernel_ints_{kernel_size}_train.npy"), kernels_train)
        np.save(os.path.join("datasets", "translator_data", f"kernel_ints_{kernel_size}_val.npy"), kernels_val)
        np.save(os.path.join("datasets", "translator_data", f"kernel_ints_{kernel_size}_test.npy"), kernels_test)
        
        return
 
class KernelGen():   
    def __init__(self, kernel_size:int = 9, train:bool = True):
        self.kernel_size = kernel_size
        if train:
            self.kernel = np.load(os.path.join("datasets", "translator_data", f"kernel_ints_{self.kernel_size}_train.npy"), "r")
        else:
            self.kernel = np.load(os.path.join("datasets", "translator_data", f"kernel_ints_{self.kernel_size}_test.npy"), "r")
     
        
    def get_kernel(self, idx:int):
        # get next idx of kernel, cycle through if idx exceeds kernel length
        kernel_int = int(self.kernel[idx % len(self.kernel)]) & ((1 << (6 ** 2)) - 1)
        kernel = torch.FloatTensor([int(b) for b in format(kernel_int, f'0{6**2}b')])
        kernel = torch.nn.functional.interpolate(kernel.view(1, 1, 6, 6), size=(self.kernel_size, self.kernel_size), mode='nearest')
        kernel = (kernel - 0.5) * 2  # scale to [-1, 1]
        return kernel